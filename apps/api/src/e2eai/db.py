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


class Notification(Base):
    """In-app notification row (FR-F11/FR-C10). Details contain safe metadata only."""
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class DocPrincipal(Base):
    """Read-index for permission-filtered retrieval (PRD T4). Stores the *granted principal*
    (user:/team:/division:/role:/org:), never expanded to individual users."""
    __tablename__ = "doc_principals"
    __table_args__ = (Index("doc_principals_by_principal", "principal", "document_id"),)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="viewer")  # viewer/editor/owner
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    """FR-C11: user-owned chat conversation. CRUD is scoped to user_id."""
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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


class Bot(Base):
    """FR-RL1/FR-RL7: bot container with one production bundle pointer."""
    __tablename__ = "bots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    production_bundle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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


class BotGrant(Base):
    """Principals allowed to use a bot. Grants are not expanded per user."""
    __tablename__ = "bot_grants"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(32), default="user")


class BotScope(Base):
    """Knowledge scope entries for a bot. Effective retrieval = bot scope ∩ user permissions."""
    __tablename__ = "bot_scopes"
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), primary_key=True)  # document/folder
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


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
