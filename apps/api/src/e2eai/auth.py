"""Local accounts, Valkey-backed sessions, CSRF, and a login rate-limit placeholder (PRD T2 auth,
NFR-18). Pure helpers (hashing, CSRF, rate limit, session store) are testable without secrets; the
router wires them to the live DB and Valkey."""

import json
import secrets
import uuid
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlencode

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .core.config import get_settings
from .core.errors import AppError
from .db import LocalCredential, User, get_session

COOKIE = "e2eai_session"
CSRF_HEADER = "X-CSRF-Token"
LOGIN_MAX_ATTEMPTS = 10  # ponytail: fixed-window placeholder (NFR-18, FR-F13); sliding window in P1
LOGIN_WINDOW_SECONDS = 300


@dataclass(frozen=True)
class OIDCProvider:
    """Secret-free OIDC authorization endpoint settings (FR-F1)."""

    authorization_endpoint: str
    client_id: str
    scopes: tuple[str, ...] = ("openid", "email", "profile")


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
            return {"user_id": str(user.id), "auth_type": "api_key", "scopes": list(key.scopes)}

    # Fall back to session cookie
    sid = request.cookies.get(COOKIE)
    data = await _sessions().get(sid) if sid else None
    if not data:
        raise AppError(401, "Not authenticated")
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


@router.post("/auth/login")
async def login(body: LoginIn, response: Response, db: AsyncSession = Depends(get_session)) -> dict:
    redis = redis_client()
    if not await login_allowed(redis, body.email.lower()):
        raise AppError(429, "Too many attempts", "Please wait and try again.")
    user = await authenticate(db, body.email, body.password)
    if user is None:
        await audit.record(db, body.email.lower(), "auth.login.failed", f"email:{body.email.lower()}")
        await db.commit()
        raise AppError(401, "Invalid email or password")
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
    return {"user_id": str(user.id), "email": user.email, "display_name": user.display_name}
