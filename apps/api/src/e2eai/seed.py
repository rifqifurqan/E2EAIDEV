"""Seeds: the five roles (FR-F3), the break-glass bootstrap admin (FR-F2a), and the demo org used by
the user-story and leak tests (PRD §17.2: Org "Demo"; Sales and HR; Andi, Budi, an intern). All seeds
are idempotent and generate passwords at runtime — nothing secret is committed."""

import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import hash_password
from .db import ROLE_NAMES, Division, LocalCredential, Organization, Role, User, UserRole

ADMIN_EMAIL = "admin@local.e2eai"
LEGACY_ADMIN_EMAIL = "admin@local"
DEMO_ORG = "Demo"
DEMO_DIVISIONS = ("Sales", "HR")
# (display name, email, division, role) — personas for the permission-leak suite (FR-T7).
DEMO_USERS = (
    ("Andi", "andi@demo.e2eai", "Sales", "business_user"),
    ("Budi", "budi@demo.e2eai", "HR", "business_user"),
    ("Intern", "intern@demo.e2eai", "Sales", "business_user"),
)


def gen_password() -> str:
    """URL-safe, so it is shell/DSN-safe per AGENTS.md secret rules."""
    return secrets.token_urlsafe(18)


async def seed_roles(session: AsyncSession) -> None:
    have = set(await session.scalars(select(Role.name)))
    for name in ROLE_NAMES:
        if name not in have:
            session.add(Role(name=name))
    await session.flush()


async def bootstrap_admin(session: AsyncSession, password: str | None = None) -> str | None:
    """Create the break-glass admin once. Returns the generated password, or None if it already exists."""
    await seed_roles(session)
    if await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL)):
        return None
    legacy_admin = await session.scalar(select(User).where(func.lower(User.email) == LEGACY_ADMIN_EMAIL))
    if legacy_admin is not None:
        legacy_admin.email = ADMIN_EMAIL
        await audit.record(session, "bootstrap", "admin.email_migrated", f"user:{legacy_admin.id}")
        await session.commit()
        return None
    password = password or gen_password()
    org = await session.scalar(select(Organization).where(Organization.name == "System"))
    if org is None:
        org = Organization(name="System", created_by="bootstrap")
        session.add(org)
        await session.flush()
    admin_role = await session.scalar(select(Role).where(Role.name == "admin"))
    user = User(org_id=org.id, email=ADMIN_EMAIL, display_name="Bootstrap Admin", created_by="bootstrap")
    session.add(user)
    await session.flush()
    session.add(LocalCredential(user_id=user.id, password_hash=hash_password(password)))
    session.add(UserRole(user_id=user.id, role_id=admin_role.id))
    await audit.record(session, "bootstrap", "admin.bootstrap", f"user:{user.id}")
    await session.commit()
    return password


async def reset_admin_password(session: AsyncSession, password: str | None = None) -> str:
    """Reset (or create) the browser-login admin password. Returns the new plaintext password.

    If the admin user does not exist yet, delegates to bootstrap_admin.
    If it does exist, overwrites the stored credential hash. Older dev databases used
    ``admin@local``, which Pydantic/FastAPI rejects as an email address; migrate that
    row to ``ADMIN_EMAIL`` so the live web login form can use it.
    """
    existing = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    if existing is None:
        existing = await session.scalar(select(User).where(func.lower(User.email) == LEGACY_ADMIN_EMAIL))
        if existing is not None:
            existing.email = ADMIN_EMAIL
    if existing is None:
        result = await bootstrap_admin(session, password)
        # bootstrap_admin always returns the password when creating
        return result  # type: ignore[return-value]
    password = password or gen_password()
    cred = await session.scalar(select(LocalCredential).where(LocalCredential.user_id == existing.id))
    if cred is None:
        session.add(LocalCredential(user_id=existing.id, password_hash=hash_password(password)))
    else:
        cred.password_hash = hash_password(password)
    await audit.record(session, "operator", "admin.password_reset", f"user:{existing.id}")
    await session.commit()
    return password


async def seed_demo(session: AsyncSession, password: str | None = None) -> str | None:
    """Create the demo org and its users (one shared password). Returns it, or None if already seeded."""
    if await session.scalar(select(Organization).where(Organization.name == DEMO_ORG)):
        return None
    await seed_roles(session)
    password = password or gen_password()
    org = Organization(name=DEMO_ORG, created_by="seed")
    session.add(org)
    await session.flush()
    divisions = {name: Division(org_id=org.id, name=name, created_by="seed") for name in DEMO_DIVISIONS}
    session.add_all(divisions.values())
    await session.flush()
    roles = {r.name: r for r in await session.scalars(select(Role))}
    pw_hash = hash_password(password)
    for display_name, email, division, role in DEMO_USERS:
        user = User(org_id=org.id, email=email, display_name=display_name,
                    division_id=divisions[division].id, created_by="seed")
        session.add(user)
        await session.flush()
        session.add(LocalCredential(user_id=user.id, password_hash=pw_hash))
        session.add(UserRole(user_id=user.id, role_id=roles[role].id))
    await audit.record(session, "seed", "org.seed", f"org:{org.id}", {"users": len(DEMO_USERS)})
    await session.commit()
    return password
