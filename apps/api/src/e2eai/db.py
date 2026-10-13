"""Database engine, sessions, and the Phase 0 tables (PRD T3). One models module until a module needs its own."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
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


# NFR-20: tables that intentionally do not carry created/updated by and at, with the reason.
AUDIT_EXEMPT_TABLES: dict[str, str] = {
    "audit_log": "append-only hash chain; each entry already records its own time (at) and actor",
}


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Project(Audited, Base):
    """FR-F2/FR-F3 project container for scoped Lab roles."""
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "name", name="projects_org_name_unique"),)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    owner_division_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("divisions.id"))


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class LocalCredential(Base):
    __tablename__ = "local_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Folder(Audited, Base):
    """Shareable container (PRD T3). Sharing a folder shares its contents (FR-S3)."""
    __tablename__ = "folders"
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("folders.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(1000), default="/")


class FolderPrincipal(Base):
    """Read-index for inherited folder sharing (FR-S3).

    Stores the granted principal, not expanded users. Retrieval/list views join this table in the SQL
    permission predicate, so folder shares never copy embeddings or disclose folder contents to others.
    """
    __tablename__ = "folder_principals"
    __table_args__ = (Index("folder_principals_by_principal", "principal", "folder_id"),)
    folder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="viewer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Notification(Base):
    """In-app notification row (FR-F11/FR-C10). Details contain safe metadata only."""
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


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
    # FR-D8: review owner / next review date / expiry. Expired documents are excluded from retrieval.
    review_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class ChunkEmbedding(Base):
    """One embedding vector per chunk/model. Shares never copy embeddings per user (FR-C1).

    `vector` is a real pgvector column (filterable/orderable by `<=>`). Dimension is left unspecified
    so the one embedding model selected at install time sets it; a fixed-dim per-index table with an
    HNSW index (PRD T3 `emb_<index_id>`) lands with multi-index support (FR-R1/US7).
    """
    __tablename__ = "chunk_embeddings"
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(160))
    dims: Mapped[int] = mapped_column(Integer)
    # ponytail: unspecified-dim vector = exact scan, no HNSW. Fine at tracer-bullet scale; add the
    # fixed-dim per-index table + HNSW when a second embedding model or >~1M chunks lands.
    vector: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class IndexLineage(Base):
    """FR-D10: one row per (document version, embedding model) index build.

    Records the parser, chunker, and embedding model that produced the indexed chunks, so every
    index version can be traced back to its sources. Metadata only: no titles, text, or vectors.
    """
    __tablename__ = "index_lineage"
    __table_args__ = (UniqueConstraint("version_id", "embedding_model", name="index_lineage_version_model"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    parser: Mapped[str] = mapped_column(String(80))
    chunker: Mapped[str] = mapped_column(String(40))
    embedding_model: Mapped[str] = mapped_column(String(160))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class DocPrincipal(Base):
    """Read-index for permission-filtered retrieval (PRD T4). Stores the *granted principal*
    (user:/team:/division:/role:/org:), never expanded to individual users."""
    __tablename__ = "doc_principals"
    __table_args__ = (Index("doc_principals_by_principal", "principal", "document_id"),)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="viewer")  # viewer/editor/owner
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Conversation(Base):
    """FR-C11: user-owned chat conversation. CRUD is scoped to user_id."""
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500))
    # FR-D13: a conversation under legal hold cannot be deleted by the user or the retention sweep.
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Message(Base):
    """PRD T3 messages: role (user/assistant), content, model metadata, stop_reason (FR-C9)."""
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(160))
    tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class MessageCitation(Base):
    """PRD T3 citations: links an assistant message to the document/version/chunk it cited."""
    __tablename__ = "message_citations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_versions.id"))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id"))
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class MessageFeedback(Base):
    """FR-O2: thumbs up/down + optional PII-masked correction, attached to the trace."""
    __tablename__ = "message_feedback"
    __table_args__ = (CheckConstraint("rating in ('up', 'down')", name="message_feedback_rating"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), unique=True)
    rating: Mapped[str] = mapped_column(String(8))
    correction_masked: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class EvalDataset(Base):
    """FR-T1/FR-D12: versioned eval dataset, manual/synthetic/trace sourced."""
    __tablename__ = "eval_datasets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))
    items: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))


class EvalRun(Base):
    """FR-T2/FR-T7/FR-T12: normalized eval run results for adapter comparisons."""
    __tablename__ = "eval_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eval_datasets.id", ondelete="SET NULL"))
    adapter: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    item_results: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))


class AccessRequest(Base):
    """FR-S5: a user requests access to a document, owner approves or denies."""
    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint("status in ('pending', 'approved', 'denied')", name="access_requests_status"),
        Index("access_requests_document_requester", "document_id", "requester_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Bot(Base):
    """FR-RL1/FR-RL7: bot container with one production bundle pointer."""
    __tablename__ = "bots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    production_bundle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class BotBundle(Base):
    """Immutable versioned bot bundle: prompt/model/index/reranker/guardrails/tools/config."""
    __tablename__ = "bot_bundles"
    __table_args__ = (Index("bot_bundles_bot_version", "bot_id", "version", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    bundle: Mapped[dict] = mapped_column(JSONB, default=dict)
    released_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class BotGrant(Base):
    """Principals allowed to use a bot. Grants are not expanded per user."""
    __tablename__ = "bot_grants"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(32), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class BotRiskClassification(Base):
    """FR-P2: AI risk classification per bot.

    Stores EU AI Act tier, NIST AI RMF profile metadata, UU PDP impact summary,
    and the release-gate requirements derived from the risk tier. No raw prompts,
    traces, documents, credentials, or user-data samples are stored here.
    """
    __tablename__ = "bot_risk_classifications"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    eu_ai_act_tier: Mapped[str] = mapped_column(String(32))
    nist_ai_rmf_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    uu_pdp_data_impact: Mapped[str] = mapped_column(Text, default="")
    pdp_impact_level: Mapped[str] = mapped_column(String(32), default="none")
    required_release_gates: Mapped[dict] = mapped_column(JSONB, default=dict)
    classified_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class ModelRegistryEntry(Base):
    """FR-M7: versioned model registry entry with lineage, eval scores, and approval status.

    Metadata only: lineage and eval scores are sanitized; no weights, prompts, or credentials.
    """
    __tablename__ = "model_registry_entries"
    __table_args__ = (
        UniqueConstraint("name", "version", name="model_registry_name_version"),
        CheckConstraint("approval_status in ('pending', 'approved', 'rejected')", name="model_registry_approval_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(64))
    parent_version: Mapped[str | None] = mapped_column(String(64))
    lineage: Mapped[dict] = mapped_column(JSONB, default=dict)
    eval_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    approval_status: Mapped[str] = mapped_column(String(16), default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(80))
    registered_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class AIIncident(Base):
    """FR-O8: AI incident record (report -> severity -> linked traces -> fix -> release -> post-incident).

    Free text is redacted for credential markers; traces are linked by id only (no content).
    """
    __tablename__ = "ai_incidents"
    __table_args__ = (
        CheckConstraint("severity in ('sev1', 'sev2', 'sev3', 'sev4')", name="ai_incidents_severity"),
        CheckConstraint(
            "status in ('reported', 'triaged', 'fixing', 'fixed', 'released', 'closed')", name="ai_incidents_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="reported")
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"))
    trace_ids: Mapped[list] = mapped_column(JSONB, default=list)
    assignee_id: Mapped[str | None] = mapped_column(String(80))
    fix_notes: Mapped[str | None] = mapped_column(Text)
    release_ref: Mapped[str | None] = mapped_column(String(200))
    postmortem: Mapped[dict | None] = mapped_column(JSONB)
    reported_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class FlywheelItem(Base):
    """FR-I1: flagged answer in the improvement triage queue.

    Holds PII-masked question/correction text and ids only; the assistant answer is never stored.
    """
    __tablename__ = "flywheel_items"
    __table_args__ = (
        CheckConstraint(
            "source in ('thumbs_down', 'low_online_score', 'reviewer_flag')", name="flywheel_items_source"
        ),
        CheckConstraint(
            "status in ('queued', 'accepted', 'dismissed', 'exported', 'reevaluated', 'released')",
            name="flywheel_items_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    source: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), unique=True)
    trace_id: Mapped[str | None] = mapped_column(String(120))
    question_masked: Mapped[str] = mapped_column(Text)
    correction_masked: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(300))
    target: Mapped[str | None] = mapped_column(String(16))
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eval_datasets.id", ondelete="SET NULL"))
    eval_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("eval_runs.id", ondelete="SET NULL"))
    release_ref: Mapped[str | None] = mapped_column(String(200))
    triaged_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class ConnectorDocument(Base):
    """FR-X1: maps a source-system document (connector + external id) to a local document.

    Metadata only: no credentials, tokens, or source URLs are stored.
    """
    __tablename__ = "connector_documents"
    __table_args__ = (UniqueConstraint("source", "external_id", name="connector_documents_source_external"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    source: Mapped[str] = mapped_column(String(120))
    external_id: Mapped[str] = mapped_column(String(300))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    content_sha256: Mapped[str] = mapped_column(String(64))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class AIInventoryEntry(Base):
    """FR-P3: AI inventory entry with model-card and system-card metadata.

    Stores safe governance metadata for a bot/system or standalone model. Cards
    deliberately avoid prompts, traces, document text, credentials, and raw user
    data; service helpers sanitize input before persisting.
    """
    __tablename__ = "ai_inventory_entries"
    __table_args__ = (
        CheckConstraint("kind in ('bot', 'model')", name="ai_inventory_entries_kind"),
        CheckConstraint("status in ('draft', 'active', 'retired')", name="ai_inventory_entries_status"),
        CheckConstraint("approval_status in ('not_required', 'pending', 'approved', 'rejected')", name="ai_inventory_entries_approval_status"),
        Index("ai_inventory_entries_kind_name", "kind", "name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(16))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    risk_tier: Mapped[str] = mapped_column(String(32), default="minimal")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    approval_status: Mapped[str] = mapped_column(String(16), default="not_required")
    model_card: Mapped[dict] = mapped_column(JSONB, default=dict)
    system_card: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[str | None] = mapped_column(String(80))


class BotApproval(Base):
    """FR-P4: approval workflow record for high-risk bot releases.

    Stores only governance metadata and sanitized rationale/decision notes. Raw
    prompts, traces, documents, user data, and credentials do not belong here.
    """
    __tablename__ = "bot_approvals"
    __table_args__ = (
        CheckConstraint("approval_type in ('high_risk_release')", name="bot_approvals_type"),
        CheckConstraint("status in ('pending', 'approved', 'rejected')", name="bot_approvals_status"),
        Index("bot_approvals_bot_status", "bot_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    approval_type: Mapped[str] = mapped_column(String(32), default="high_risk_release")
    risk_tier: Mapped[str] = mapped_column(String(32), default="minimal")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    rationale: Mapped[str] = mapped_column(Text, default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(80))
    decided_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class BotScope(Base):
    """Knowledge scope entries for a bot. Effective retrieval = bot scope ∩ user permissions."""
    __tablename__ = "bot_scopes"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), primary_key=True)  # document/folder
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class BotEnvironment(Base):
    """FR-RL6: per-environment deployment pointer (dev/staging/prod).

    Promotion repoints an environment at an immutable bundle; it never edits the bundle in place.
    Lite tier uses a single environment where the prod pointer / production_bundle_id still applies.
    """
    __tablename__ = "bot_environments"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    environment: Mapped[str] = mapped_column(String(16), primary_key=True)  # dev/staging/prod
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    allow_production_data: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class ApiKey(Base):
    """FR-F12: scoped API keys for public REST clients. Raw key is never stored — only sha256 hash.
    Prefix (first 12 chars) is stored for display/identification purposes."""
    __tablename__ = "api_keys"
    __table_args__ = (Index("api_keys_key_hash", "key_hash", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    key_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    prefix: Mapped[str] = mapped_column(String(16))  # first 12 chars for display
    scopes: Mapped[list] = mapped_column(JSONB, default=list)  # ["chat", "documents", ...]
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class Prompt(Base):
    """FR-B1: prompt registry entry owned by a user/team module actor."""
    __tablename__ = "prompts"
    __table_args__ = (Index("prompts_owner_name", "owner_id", "name", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class PromptVersion(Base):
    """Immutable prompt text version. Labels point at versions instead of mutating them."""
    __tablename__ = "prompt_versions"
    __table_args__ = (Index("prompt_versions_prompt_version", "prompt_id", "version", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))


class PromptLabel(Base):
    """Named pointer such as production/staging to a prompt version (FR-B1)."""
    __tablename__ = "prompt_labels"
    __table_args__ = (UniqueConstraint("prompt_id", "label", name="prompt_labels_prompt_label"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(64))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    updated_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))


class SloAlert(Base):
    """FR-O5: persisted SLO alert — safe storage only.

    Stores alert name, actual metric value, threshold, and window metadata.
    Never stores message content, prompts, answers, document text, tokens, secrets, or credentials.
    """
    __tablename__ = "slo_alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    alert_name: Mapped[str] = mapped_column(String(80))
    actual: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))


class FinopsBudgetAlert(Base):
    """FR-O6: persisted FinOps budget alert — safe storage only.

    Stores the breaching dimension, entity id, actual spend, threshold, and window metadata.
    Never stores message content, prompts, answers, document text, model names, tokens,
    secrets, or credentials.
    """
    __tablename__ = "finops_budget_alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    dimension: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(80))
    actual: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(80))


class McpToolCall(Base):
    """FR-X2: persisted safe record of a planned+executed MCP tool call at question time.

    Stores only safe metadata: system/operation IDs, method, path, flags, and a safe result summary.
    Never stores auth secrets, server URLs, raw user question, bearer tokens, API keys, or payloads.
    """
    __tablename__ = "mcp_tool_calls"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    system_id: Mapped[str] = mapped_column(String(80))
    operation_id: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(500))
    read_only: Mapped[bool] = mapped_column(Boolean)
    needs_confirmation: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32), default="planned")
    safe_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    auth_mode: Mapped[str | None] = mapped_column(String(32))  # FR-X3: delegated/token_exchange/None
    acting_user_id: Mapped[str | None] = mapped_column(String(80))  # FR-X3: user who the AI acts as
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class SystemRegistration(Audited, Base):
    """FR-X4: admin-registered external system (ERP, HR, CRM).

    Stores safe configuration metadata only: name, description, spec hash, allowed
    operations, auth mode hint. Never stores raw credentials, bearer tokens, API keys,
    passwords, server URLs, or the raw OpenAPI spec text.
    """
    __tablename__ = "system_registrations"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="registered")
    spec_hash: Mapped[str | None] = mapped_column(String(64))
    discovered_operations: Mapped[list] = mapped_column(JSONB, default=list)
    allowed_operations: Mapped[list] = mapped_column(JSONB, default=list)
    auth_config: Mapped[dict] = mapped_column(JSONB, default=dict)


class UseCaseIntake(Audited, Base):
    """FR-P1: Plan-stage use-case intake form.

    Stores planning metadata: problem, intended users, success metrics, data sources,
    and systems to integrate. It must never store credentials, tokens, or connection
    strings supplied by mistake in form metadata.
    """
    __tablename__ = "use_case_intakes"
    __table_args__ = (CheckConstraint("status in ('draft', 'submitted')", name="use_case_intakes_status"),)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    problem: Mapped[str] = mapped_column(Text)
    users: Mapped[list] = mapped_column(JSONB, default=list)
    success_metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    data_sources: Mapped[list] = mapped_column(JSONB, default=list)
    systems_to_integrate: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="submitted")


class UserMemorySetting(Base):
    """FR-B2: per-user opt-in switch for long-term memory (off by default)."""
    __tablename__ = "user_memory_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class UserMemory(Base):
    """FR-B2: one long-term memory item owned by a user (PII-masked, secret-redacted text only)."""
    __tablename__ = "user_memories"
    __table_args__ = (Index("user_memories_user_idx", "user_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class DataSubjectRequest(Base):
    """NFR-10: ledger of data-subject requests (export/erase) with a response deadline. Ids and labels only."""
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint("kind in ('export', 'erase')", name="dsr_kind"),
        CheckConstraint("status in ('open', 'completed')", name="dsr_status"),
        Index("dsr_created_idx", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(10), default="open")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by: Mapped[str] = mapped_column(String(80))
    last_reminder: Mapped[str | None] = mapped_column(String(10))  # 'due_soon' | 'overdue': reminders are sent once per state
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class SystemGrant(Base):
    """FR-X4: principals (role/division) granted access to a registered system."""
    __tablename__ = "system_grants"
    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("system_registrations.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


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

from .core import audit_actor as _audit_actor  # noqa: E402,F401  (registers the created_by/updated_by hook)
