"""US13 / FR-F18: user offboarding P0 — deactivate, revoke sessions, transfer docs, retain chats.

TDD RED: these tests define the offboarding behavior before any implementation exists.
They run against the real DB + pgvector path and use a fake Valkey (dict-backed) for session tests.
"""

import asyncio
import subprocess
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from e2eai.auth import Sessions, hash_password
from e2eai.authz import principals
from e2eai.core.errors import AppError
from e2eai.db import (
    AuditEntry, Chunk, ChunkEmbedding, Conversation, DocPrincipal, Document,
    DocumentVersion, Folder, FolderPrincipal, LocalCredential, Message, User,
    sessions as db_sessions,
)
from e2eai.documents import (
    LocalObjectStorage, create_seeded_document, create_uploaded_document,
    share_document, visible_chunks,
)
from e2eai.ingest import ingest_version
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo

REVENUE = "The WhatsApp partnership revenue share is 30 percent."
QUESTION = "What is the revenue share in the WhatsApp partnership?"


def teardown_module(module):
    """Reset any disabled users so subsequent test files in the suite find active demo users."""
    import asyncio
    from sqlalchemy import update as sql_update
    async def _cleanup():
        async with db_sessions()() as session:
            await session.execute(sql_update(User).where(User.status == "disabled").values(status="active"))
            await session.commit()
    asyncio.run(_cleanup())


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


class FakeRedis:
    """Dict-backed fake that supports the subset of Redis commands used by Sessions and offboarding."""

    def __init__(self):
        self._data: dict[str, str] = {}
        self._ttls: dict[str, int] = {}
        self._sets: dict[str, set[str]] = {}

    async def set(self, key, value, ex=None):
        self._data[key] = value
        if ex:
            self._ttls[key] = ex

    async def get(self, key):
        return self._data.get(key)

    async def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)
            self._ttls.pop(k, None)

    async def expire(self, key, seconds):
        self._ttls[key] = seconds

    async def incr(self, key):
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    async def sadd(self, key, *members):
        self._sets.setdefault(key, set()).update(members)

    async def smembers(self, key):
        return self._sets.get(key, set())

    async def srem(self, key, *members):
        s = self._sets.get(key, set())
        for m in members:
            s.discard(m)

    async def scan(self, cursor=0, match=None, count=100):
        # Simple scan implementation for tests
        keys = list(self._data.keys())
        if match:
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        return (0, keys)


async def _audit_count(session, action, target=None):
    stmt = select(func.count()).select_from(AuditEntry).where(AuditEntry.action == action)
    if target:
        stmt = stmt.where(AuditEntry.target == target)
    return await session.scalar(stmt)


async def _reset(session):
    for model in (Message, Conversation, ChunkEmbedding, FolderPrincipal, DocPrincipal,
                  Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    # Reset any previously disabled users back to active so tests are independent
    from sqlalchemy import update
    await session.execute(update(User).where(User.status == "disabled").values(status="active"))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    intern_ = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    return andi, budi, intern_


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


# ---------------------------------------------------------------------------
# Test 1: Deactivate sets status=disabled and purges all sessions
# ---------------------------------------------------------------------------

def test_deactivate_sets_disabled_and_purges_sessions():
    """Admin deactivates Andi. His status becomes 'disabled' and all his Valkey sessions are deleted."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            # Create sessions for Andi
            fake_redis = FakeRedis()
            store = Sessions(fake_redis, 28800)
            sid1, _ = await store.create(str(andi.id))
            sid2, _ = await store.create(str(andi.id))
            # Verify sessions exist
            assert await store.get(sid1) is not None
            assert await store.get(sid2) is not None

            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            await session.refresh(andi)
            assert andi.status == "disabled"

            # All sessions for Andi must be gone
            assert await store.get(sid1) is None
            assert await store.get(sid2) is None

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 2: Disabled user cannot authenticate and principals() returns empty
# ---------------------------------------------------------------------------

def test_disabled_user_cannot_authenticate_and_has_empty_principals():
    """A disabled user fails login and gets an empty principal set (already enforced by authz.py)."""
    from e2eai.auth import authenticate
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            await session.refresh(andi)
            # Login returns None for disabled users
            result = await authenticate(session, "andi@demo.e2eai", "TestPassword_123456789")
            assert result is None

            # principals() returns empty set for disabled users
            p = await principals(session, andi)
            assert p == set()

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 3: Document ownership transfers; existing shares stay intact
# ---------------------------------------------------------------------------

def test_document_transfer_preserves_existing_shares(tmp_path):
    """Andi's documents transfer to Budi. Intern's share (viewer) stays intact.
    After transfer, Budi is the new owner and Intern can still retrieve the doc."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            storage = LocalObjectStorage(tmp_path / "objects")
            # Andi owns a document, shared with Intern
            doc = await create_uploaded_document(
                session, owner=andi, title="deal.txt",
                data=REVENUE.encode(), mime="text/plain", storage=storage,
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
            await share_document(session, RecordingAuthz(), actor=andi, document_id=doc.id,
                                 principal=f"user:{intern_.id}")

            # Intern can see the doc before offboarding
            intern_chunks_before = await visible_chunks(session, await principals(session, intern_))
            assert len(intern_chunks_before) > 0

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            await session.refresh(doc)
            # Owner changed to Budi
            assert doc.owner_id == budi.id

            # Budi has an owner principal on the document
            budi_owner = await session.scalar(
                select(DocPrincipal).where(
                    DocPrincipal.document_id == doc.id,
                    DocPrincipal.principal == f"user:{budi.id}",
                    DocPrincipal.level == "owner",
                )
            )
            assert budi_owner is not None

            # Andi's old owner principal is removed
            andi_owner = await session.scalar(
                select(DocPrincipal).where(
                    DocPrincipal.document_id == doc.id,
                    DocPrincipal.principal == f"user:{andi.id}",
                    DocPrincipal.level == "owner",
                )
            )
            assert andi_owner is None

            # Intern's share is still intact
            intern_share = await session.scalar(
                select(DocPrincipal).where(
                    DocPrincipal.document_id == doc.id,
                    DocPrincipal.principal == f"user:{intern_.id}",
                )
            )
            assert intern_share is not None

            # Intern can still retrieve the doc
            intern_chunks_after = await visible_chunks(session, await principals(session, intern_))
            assert len(intern_chunks_after) > 0
            assert intern_chunks_after[0][0] == "deal.txt"

            # Budi can also retrieve the doc as the new owner
            budi_chunks = await visible_chunks(session, await principals(session, budi))
            assert len(budi_chunks) > 0

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 4: Folder ownership transfers too
# ---------------------------------------------------------------------------

def test_folder_ownership_transfers(tmp_path):
    """Andi's folders transfer to Budi."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            folder = Folder(owner_id=andi.id, name="Andi's deals", path="/deals", created_by=str(andi.id))
            session.add(folder)
            await session.commit()

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            await session.refresh(folder)
            assert folder.owner_id == budi.id

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 5: Chats retained but inaccessible to deactivated user
# ---------------------------------------------------------------------------

def test_chats_retained_but_inaccessible_after_deactivation():
    """Andi's conversations are retained (not deleted) but inaccessible because
    his status is disabled and _current_user / _own_conversation reject disabled users."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            # Create a conversation for Andi
            conv = Conversation(user_id=andi.id, title="Sales chat")
            session.add(conv)
            await session.flush()
            msg = Message(conversation_id=conv.id, role="user", content="Hello")
            session.add(msg)
            await session.commit()

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # Conversation and messages still exist in the DB (retention)
            conv_row = await session.get(Conversation, conv.id)
            assert conv_row is not None
            msg_count = await session.scalar(
                select(func.count()).select_from(Message)
                .where(Message.conversation_id == conv.id)
            )
            assert msg_count == 1

            # But Andi's status is disabled, so chat service functions reject him
            await session.refresh(andi)
            assert andi.status == "disabled"
            # principals() returns empty for disabled users
            assert await principals(session, andi) == set()

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 6: Placeholder API key and token revocation is audited
# ---------------------------------------------------------------------------

def test_placeholder_key_token_revocation_audited():
    """Even though the key/token system isn't built yet, deactivation creates explicit
    placeholder audit rows so the revocation intent is recorded and testable."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # Placeholder revocation audit rows exist (count >= 1 from this + prior test runs;
            # the audit log is append-only)
            api_key_revoke = await _audit_count(session, "user.api_keys.revoked", f"user:{andi.id}")
            assert api_key_revoke >= 1
            token_revoke = await _audit_count(session, "user.delegated_tokens.revoked", f"user:{andi.id}")
            assert token_revoke >= 1

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 7: Offboarding audit captures the action without sensitive content
# ---------------------------------------------------------------------------

def test_offboarding_audit_captures_action_without_sensitive_content():
    """The admin offboarding action is audited with safe metadata only."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # Main offboarding audit entry
            entry = await session.scalar(
                select(AuditEntry).where(
                    AuditEntry.action == "user.offboard",
                    AuditEntry.target == f"user:{andi.id}",
                )
            )
            assert entry is not None
            assert entry.actor == f"user:{budi.id}"
            details = entry.details
            assert "transfer_to" in details
            assert details["transfer_to"] == str(budi.id)
            # No passwords, tokens, or raw session IDs in audit. The key "sessions_purged"
            # stores only a count (safe metadata), not actual session tokens.
            details_str = str(details)
            assert "password" not in details_str.lower()
            assert "token" not in details_str.lower()
            # Verify sessions_purged is an integer count, not a session ID
            assert isinstance(details.get("sessions_purged"), int)

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 8: No-existence-leak after deactivation (Andi's doc perspective)
# ---------------------------------------------------------------------------

def test_no_leak_after_deactivation(tmp_path):
    """After Andi is deactivated, his retrieval/citations return nothing.
    Budi (who never had access) still sees nothing — no existence hints."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=andi, title="deal.txt",
                data=REVENUE.encode(), mime="text/plain", storage=storage,
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)

            # Before deactivation, Andi can see the doc
            andi_before = await visible_chunks(session, await principals(session, andi))
            assert len(andi_before) > 0

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # After deactivation, Andi gets empty principals -> no chunks
            await session.refresh(andi)
            assert await principals(session, andi) == set()
            andi_after = await visible_chunks(session, await principals(session, andi))
            assert andi_after == []

            # Andi's answer has no leak
            andi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=andi, question=QUESTION
            )
            assert andi_answer["citations"] == []
            assert "WhatsApp" not in andi_answer["answer"]
            assert "30 percent" not in andi_answer["answer"]

            # Budi (new owner) can see the transferred doc
            budi_chunks = await visible_chunks(session, await principals(session, budi))
            assert len(budi_chunks) > 0

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 9: OpenFGA owner tuples are updated for transferred documents
# ---------------------------------------------------------------------------

def test_openfga_owner_tuples_updated():
    """The offboarding writes OpenFGA deletes for the old owner and writes for the new owner."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            # Create two documents owned by Andi
            doc1 = await create_seeded_document(session, owner=andi, title="Doc 1", text="content 1")
            doc2 = await create_seeded_document(session, owner=andi, title="Doc 2", text="content 2")

            fake_redis = FakeRedis()
            authz = RecordingAuthz()
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # Check OpenFGA calls: should have deletes for Andi's owner tuples
            # and writes for Budi's owner tuples
            all_writes = []
            all_deletes = []
            for call in authz.calls:
                all_writes.extend(call.get("writes", []))
                all_deletes.extend(call.get("deletes", []))

            # Andi's owner tuples deleted
            andi_deletes = [d for d in all_deletes if d["user"] == f"user:{andi.id}" and d["relation"] == "owner"]
            assert len(andi_deletes) == 2

            # Budi's owner tuples written
            budi_writes = [w for w in all_writes if w["user"] == f"user:{budi.id}" and w["relation"] == "owner"]
            assert len(budi_writes) == 2

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test 10: Cannot deactivate self or already-disabled user
# ---------------------------------------------------------------------------

def test_cannot_deactivate_self_or_already_disabled():
    """Guard: admin cannot deactivate themselves, and deactivating an already-disabled user is a no-op error."""
    from e2eai.offboarding import deactivate_user

    async def run():
        async with db_sessions()() as session:
            await _reset(session)
            andi, budi, intern_ = await _users(session)

            fake_redis = FakeRedis()
            authz = RecordingAuthz()

            # Cannot deactivate self
            with pytest.raises(AppError) as ei:
                await deactivate_user(
                    session, fake_redis, authz,
                    admin=andi, target_user_id=andi.id, transfer_to_id=budi.id,
                )
            assert ei.value.status == 400

            # Deactivate Andi first
            await deactivate_user(
                session, fake_redis, authz,
                admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
            )

            # Re-deactivating raises 409
            with pytest.raises(AppError) as ei:
                await deactivate_user(
                    session, fake_redis, authz,
                    admin=budi, target_user_id=andi.id, transfer_to_id=budi.id,
                )
            assert ei.value.status == 409

    _migrate()
    asyncio.run(run())
