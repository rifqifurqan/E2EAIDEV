"""Local accounts, Valkey-backed sessions, CSRF, and a login rate-limit placeholder (PRD T2 auth,
NFR-18). Pure helpers (hashing, CSRF, rate limit, session store) are testable without secrets; the
router wires them to the live DB and Valkey."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlencode

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .core.audit_actor import set_actor
from .core.config import get_settings
from .core.errors import AppError
from .db import LocalCredential, Organization, User, get_session

COOKIE = "e2eai_session"
CSRF_HEADER = "X-CSRF-Token"
LOGIN_MAX_ATTEMPTS = 10  # ponytail: fixed-window placeholder (NFR-18, FR-F13); sliding window in P1
LOGIN_WINDOW_SECONDS = 300
LOGIN_IP_MAX_ATTEMPTS = 50  # per client address; higher than the per-account limit so an office NAT is not locked out


@dataclass(frozen=True)
class OIDCProvider:
    """Secret-aware OIDC endpoint settings (FR-F1); repr never exposes the client secret."""

    authorization_endpoint: str
    client_id: str
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    client_secret: str = field(default="", repr=False)
    scopes: tuple[str, ...] = ("openid", "email", "profile")


@dataclass(frozen=True)
class OIDCIdentity:
    """Validated identity returned by Keycloak's userinfo endpoint. Contains no tokens."""

    sub: str
    email: str
    display_name: str


def build_oidc_authorization_url(
    provider: OIDCProvider,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str | None = None,
) -> str:
    """Build a browser redirect URL for OIDC code flow without client secrets.

    Token exchange is intentionally outside this helper so secrets never enter logs, tests, or URLs.
    """
    if not provider.authorization_endpoint or not provider.client_id:
        raise AppError(503, "OIDC provider is not configured")
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(provider.scopes),
        "state": state,
        "nonce": nonce,
    }
    if code_challenge:
        params |= {"code_challenge": code_challenge, "code_challenge_method": "S256"}
    return f"{provider.authorization_endpoint}?{urlencode(params)}"


def oidc_provider_from_settings() -> OIDCProvider:
    """Build OIDC endpoint config from e2eai.yaml/env without logging or returning secrets."""
    settings = get_settings()
    return OIDCProvider(
        authorization_endpoint=settings.oidc_authorization_endpoint,
        token_endpoint=settings.oidc_token_endpoint,
        userinfo_endpoint=settings.oidc_userinfo_endpoint,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
    )


def _idp_unavailable() -> AppError:
    return AppError(503, "Identity provider unavailable",
                    "The sign-in service did not respond. Please try again shortly.", "upstream-unavailable")


async def exchange_oidc_code_for_identity(
    http_client,
    provider: OIDCProvider,
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
    retry_sleep=None,
) -> OIDCIdentity:
    """Exchange an authorization code with Keycloak and validate it via userinfo.

    Keycloak validates the code, client, redirect URI, PKCE verifier, and access token. The API then
    trusts only the token-authenticated userinfo response and never stores or returns raw tokens.
    """
    if not provider.token_endpoint or not provider.userinfo_endpoint or not provider.client_id:
        raise AppError(503, "OIDC provider is not configured")
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider.client_id,
    }
    if provider.client_secret:
        form["client_secret"] = provider.client_secret
    if code_verifier:
        form["code_verifier"] = code_verifier
    from .core.resilience import RetryExhausted, breaker_for, with_retry

    sleep_kw = {"sleep": retry_sleep} if retry_sleep else {}
    breaker = breaker_for(provider.token_endpoint, "keycloak")
    if not breaker.allow():  # fail fast while Keycloak is known to be down (NFR-19)
        err = _idp_unavailable()
        err.headers = {"Retry-After": str(breaker.retry_after())}
        raise err
    try:
        # The authorization code is single use: retry only when the request never reached Keycloak.
        token_response = await with_retry(
            lambda: http_client.post(
                provider.token_endpoint,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=None, retry_on=(httpx.ConnectError, httpx.ConnectTimeout), **sleep_kw,
        )
    except (httpx.TransportError, RetryExhausted):
        breaker.record_failure()
        raise _idp_unavailable() from None
    if token_response.status_code >= 400:
        breaker.record_success()  # the IdP answered: a bad code is not an outage
        raise AppError(401, "OIDC token exchange failed")
    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    token_type = token_payload.get("token_type", "Bearer")
    if not access_token or token_type.lower() != "bearer":
        breaker.record_success()
        raise AppError(401, "OIDC token response is invalid")
    try:
        userinfo_response = await with_retry(
            lambda: http_client.get(
                provider.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            ),
            timeout=None, retry_on=(httpx.TransportError,), **sleep_kw,
        )
    except (httpx.TransportError, RetryExhausted):
        breaker.record_failure()
        raise _idp_unavailable() from None
    breaker.record_success()
    if userinfo_response.status_code >= 400:
        raise AppError(401, "OIDC userinfo validation failed")
    userinfo = userinfo_response.json()
    sub = str(userinfo.get("sub") or "").strip()
    email = str(userinfo.get("email") or "").strip().lower()
    display_name = str(userinfo.get("name") or userinfo.get("preferred_username") or email).strip()
    if not sub or not email:
        raise AppError(401, "OIDC userinfo is missing required claims")
    return OIDCIdentity(sub=sub, email=email, display_name=display_name or email)


async def ensure_oidc_user(
    session: AsyncSession,
    identity: OIDCIdentity,
    *,
    default_org_id: uuid.UUID | None = None,
) -> User:
    """Find or create an active user for a validated OIDC identity; no local password is created."""
    user = await session.scalar(
        select(User).where(func.lower(User.email) == identity.email.lower(), User.status == "active")
    )
    if user is not None:
        return user
    org_id = default_org_id
    if org_id is None:
        org_id = await session.scalar(select(Organization.id).order_by(Organization.created_at, Organization.id).limit(1))
    if org_id is None:
        raise AppError(503, "No organization is available for OIDC user creation")
    user = User(
        org_id=org_id,
        email=identity.email.lower(),
        display_name=identity.display_name,
        status="active",
        created_by=f"oidc:{identity.sub}",
        updated_by=f"oidc:{identity.sub}",
    )
    session.add(user)
    await session.flush()
    return user


async def complete_oidc_login(
    session: AsyncSession,
    session_store: Sessions,
    http_client,
    provider: OIDCProvider,
    *,
    code: str,
    redirect_uri: str,
    default_org_id: uuid.UUID | None = None,
    code_verifier: str | None = None,
) -> tuple[User, str, str]:
    """Validate the OIDC callback, create/reuse the user, then create a local web session."""
    identity = await exchange_oidc_code_for_identity(
        http_client,
        provider,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
    user = await ensure_oidc_user(session, identity, default_org_id=default_org_id)
    sid, csrf = await session_store.create(str(user.id))
    return user, sid, csrf


def local_login_allowed(auth_provider: str, *, oidc_available: bool, is_break_glass_user: bool) -> bool:
    """Decide whether password login may be used under the configured auth mode.

    Local-only installs allow local passwords. OIDC installs keep local password login restricted to
    break-glass accounts, including when the identity provider is down; normal users must use SSO.
    ``oidc_available`` is kept explicit for audit/reasoning, but availability never widens access.
    """
    if auth_provider == "local":
        return True
    if auth_provider == "oidc":
        return is_break_glass_user
    raise AppError(500, "Unknown auth provider")


_hasher = PasswordHasher()  # argon2id defaults (PRD T9)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(expected: str, provided: str) -> bool:
    return bool(expected) and secrets.compare_digest(expected, provided)


async def login_allowed(redis: Redis, key: str,
                        limit: int = LOGIN_MAX_ATTEMPTS, window: int = LOGIN_WINDOW_SECONDS) -> bool:
    """Count attempts per key in a fixed window; deny once over the limit."""
    bucket = f"login_rl:{key}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window)
    return count <= limit


def _rl_key(kind: str, value: str) -> str:
    """Rate-limit keys hold a digest, never the raw email or address."""
    return f"login_rl:{kind}:{hashlib.sha256(value.encode()).hexdigest()[:32]}"


async def login_decision(redis: Redis, email: str, ip: str) -> tuple[bool, int]:
    """Count a login attempt against the account AND the client address (NFR-18).

    Returns ``(allowed, retry_after_seconds)``; ``retry_after`` is 0 when allowed.
    """
    retry_after = 0
    allowed = True
    for kind, value, limit in (("acct", email.strip().lower(), LOGIN_MAX_ATTEMPTS), ("ip", ip, LOGIN_IP_MAX_ATTEMPTS)):
        bucket = _rl_key(kind, value)
        count = await redis.incr(bucket)
        if count == 1:
            await redis.expire(bucket, LOGIN_WINDOW_SECONDS)
        if count > limit:
            allowed = False
            ttl = await redis.ttl(bucket)
            retry_after = max(retry_after, ttl if ttl and ttl > 0 else LOGIN_WINDOW_SECONDS)
    return allowed, (0 if allowed else max(1, retry_after))


async def clear_account_attempts(redis: Redis, email: str) -> None:
    """Forget the failed-attempt count of one account after a correct password (the address counter stays)."""
    await redis.delete(_rl_key("acct", email.strip().lower()))


@dataclass
class Sessions:
    """Server-side sessions in Valkey with a sliding idle timeout (NFR-18, default 8 h)."""
    redis: Redis
    idle_seconds: int

    async def create(self, user_id: str) -> tuple[str, str]:
        sid, csrf = new_token(), new_token()
        await self.redis.set(f"sess:{sid}", json.dumps({"user_id": user_id, "csrf": csrf}), ex=self.idle_seconds)
        return sid, csrf

    async def get(self, sid: str) -> dict | None:
        raw = await self.redis.get(f"sess:{sid}")
        if raw is None:
            return None
        await self.redis.expire(f"sess:{sid}", self.idle_seconds)  # slide the idle window on use
        return json.loads(raw)

    async def delete(self, sid: str) -> None:
        await self.redis.delete(f"sess:{sid}")


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(get_settings().valkey_url, decode_responses=True)


def _sessions() -> Sessions:
    return Sessions(redis_client(), get_settings().session_idle_hours * 3600)


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    """Return the active user if the password matches, else None (no distinction leaked to callers)."""
    user = await session.scalar(
        select(User).where(func.lower(User.email) == email.lower(), User.status == "active")
    )
    if user is None:
        return None
    cred = await session.get(LocalCredential, user.id)
    if cred is None or not verify_password(cred.password_hash, password):
        return None
    return user


def require_csrf(request: Request, sess: dict) -> None:
    if not csrf_ok(sess.get("csrf", ""), request.headers.get(CSRF_HEADER, "")):
        raise AppError(403, "CSRF token invalid")


async def current_session(request: Request) -> dict:
    """Authenticate via session cookie OR Bearer API key (FR-F12, PRD T7).

    Returns a dict with at least ``user_id``. API-key auth adds ``auth_type: "api_key"``
    and ``scopes: [...]``; cookie auth adds ``auth_type: "session"`` and ``csrf``.
    """
    # Try Bearer token first (API clients, FR-F12)
    from .api_keys import authenticate_api_key, extract_bearer_token
    from .db import get_session as _get_session

    auth_header = request.headers.get("authorization")
    token = extract_bearer_token(auth_header)
    if token:
        async for db in _get_session():
            result = await authenticate_api_key(db, token)
            if result is None:
                raise AppError(401, "Invalid API key")
            user, key = result
            set_actor(f"user:{user.id}")  # NFR-20: created_by/updated_by for this request
            return {"user_id": str(user.id), "auth_type": "api_key", "scopes": list(key.scopes)}

    # Fall back to session cookie
    sid = request.cookies.get(COOKIE)
    data = await _sessions().get(sid) if sid else None
    if not data:
        raise AppError(401, "Not authenticated")
    if data.get("user_id"):
        set_actor(f"user:{data['user_id']}")  # NFR-20: created_by/updated_by for this request
    return {"sid": sid, "auth_type": "session", **data}


def require_scope(sess: dict, scope: str) -> None:
    """Enforce that an API-key-authenticated session has the required scope (FR-F12).

    Session-based auth (web UI) has full access — scope restrictions only apply to API keys.
    """
    if sess.get("auth_type") == "api_key":
        from .api_keys import has_scope
        if not has_scope(sess.get("scopes", []), scope):
            raise AppError(403, "Insufficient scope", f"This API key does not have the '{scope}' scope.")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.get("/auth/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str,
    state: str | None = None,
    code_verifier: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Complete an OIDC code-flow login against Keycloak and create the app session."""
    settings = get_settings()
    provider = oidc_provider_from_settings()
    redirect_uri = settings.oidc_redirect_uri or f"{request.url.scheme}://{request.url.netloc}{request.url.path}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        user, sid, csrf = await complete_oidc_login(
            db,
            _sessions(),
            client,
            provider,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    idle = settings.session_idle_hours * 3600
    response.set_cookie(COOKIE, sid, max_age=idle, httponly=True, secure=True, samesite="lax")
    await audit.record(db, f"user:{user.id}", "auth.login.oidc", f"user:{user.id}", {"state_present": bool(state)})
    await db.commit()
    return {"user_id": str(user.id), "csrf_token": csrf}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_session)) -> dict:
    redis = redis_client()
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await login_decision(redis, body.email, client_ip)
    if not allowed:
        raise AppError(429, "Too many attempts", "Please wait and try again.", "about:blank",
                       headers={"Retry-After": str(retry_after)})
    user = await authenticate(db, body.email, body.password)
    if user is None:
        await audit.record(db, body.email.lower(), "auth.login.failed", f"email:{body.email.lower()}")
        await db.commit()
        raise AppError(401, "Invalid email or password")
    await clear_account_attempts(redis, body.email)
    settings = get_settings()
    is_break_glass = user.email.lower() in settings.oidc_local_fallback_emails
    if not local_login_allowed(settings.auth_provider, oidc_available=False, is_break_glass_user=is_break_glass):
        await audit.record(db, f"user:{user.id}", "auth.login.local_blocked", f"user:{user.id}", {"auth_provider": settings.auth_provider})
        await db.commit()
        raise AppError(403, "Use single sign-on", "Password login is only available for break-glass fallback accounts.")
    sid, csrf = await _sessions().create(str(user.id))
    idle = settings.session_idle_hours * 3600
    response.set_cookie(COOKIE, sid, max_age=idle, httponly=True, secure=True, samesite="lax")
    await audit.record(db, f"user:{user.id}", "auth.login", f"user:{user.id}")
    await db.commit()
    return {"user_id": str(user.id), "csrf_token": csrf}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, sess: dict = Depends(current_session)) -> dict:
    require_csrf(request, sess)
    await _sessions().delete(sess["sid"])
    response.delete_cookie(COOKIE)
    return {"status": "ok"}


@router.get("/me")
async def me(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    out = {"user_id": str(user.id), "email": user.email, "display_name": user.display_name}
    if sess.get("csrf"):  # UAT-AUTH-001: lets the web sign out after a page reload (login response is gone)
        out["csrf_token"] = sess["csrf"]
    return out
