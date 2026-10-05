"""Database engine, sessions, and the Phase 0 tables (PRD T3). One models module until a module needs its own."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from .core.config import get_settings
from .core.ids import uuid7


class Base(DeclarativeBase):
    pass


class Audited:
    """NFR-20: UUIDv7 id, UTC timestamps, who created/updated."""
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Organization(Audited, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))


class Division(Audited, Base):
    __tablename__ = "divisions"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))


class Team(Audited, Base):
    __tablename__ = "teams"
    division_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("divisions.id"))
    name: Mapped[str] = mapped_column(String(200))


class User(Audited, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status in ('active', 'disabled')", name="users_status"),
        Index("users_email_lower", text("lower(email)"), unique=True),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="active")
    division_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("divisions.id"))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    locale: Mapped[str] = mapped_column(String(8), default="id")
    time_zone: Mapped[str] = mapped_column(String(64), default="Asia/Jakarta")


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class LocalCredential(Base):
    __tablename__ = "local_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEntry(Base):
    """Append-only, hash-chained (FR-F9). Never updated or deleted."""
    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)


class Folder(Audited, Base):
    """Shareable container (PRD T3). Sharing a folder shares its contents (FR-S3)."""
    __tablename__ = "folders"
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("folders.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(1000), default="/")


class Document(Audited, Base):
    """FR-D1. Retrieval uses only the latest version (current_version_id)."""
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("status in ('active', 'trashed', 'purged')", name="documents_status"),)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("folders.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500))
    sensitivity: Mapped[str] = mapped_column(String(32), default="internal")
    status: Mapped[str] = mapped_column(String(16), default="active")
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    # ponytail: plain UUID (no FK) to avoid the documents<->document_versions circular FK; set after the version row exists.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DocumentVersion(Audited, Base):
    """FR-D1 versioning: citations in old chats keep pointing to the version they quoted."""
    __tablename__ = "document_versions"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    object_key: Mapped[str] = mapped_column(String(300))  # S3 key sha256/<hash>
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(160))
    size: Mapped[int] = mapped_column(BigInteger)
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")
    parse_confidence: Mapped[float | None] = mapped_column(Float)
    scan_status: Mapped[str] = mapped_column(String(16), default="pending")


class Chunk(Base):
    """Derived content (PRD T3). One row per text/table/figure unit. tsv + embeddings land in Phase 1."""
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text/table/figure/vlm
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(1000))
    figure_object_key: Mapped[str | None] = mapped_column(String(300))
    table_json: Mapped[dict | None] = mapped_column(JSONB)


class ChunkEmbedding(Base):
    """One embedding vector per chunk/model. Shares never copy embeddings per user (FR-C1)."""
    __tablename__ = "chunk_embeddings"
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(160))
    dims: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocPrincipal(Base):
    """Read-index for permission-filtered retrieval (PRD T4). Stores the *granted principal*
    (user:/team:/division:/role:/org:), never expanded to individual users."""
    __tablename__ = "doc_principals"
    __table_args__ = (Index("doc_principals_by_principal", "principal", "document_id"),)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="viewer")  # viewer/editor/owner
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


ROLE_NAMES = ("admin", "ai_engineer", "evaluator", "compliance", "business_user")  # FR-F3


@lru_cache
def engine() -> AsyncEngine:
    # NullPool avoids reusing asyncpg connections across event loops in pytest's asyncio.run tests
    # while keeping the app's async engine boundary explicit for the Phase 1 tracer bullet.
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, poolclass=NullPool)


@lru_cache
def sessions() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessions()() as session:
        yield session
