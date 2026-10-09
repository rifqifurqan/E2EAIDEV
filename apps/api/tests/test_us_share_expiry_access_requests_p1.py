"""P1 sharing completion: expiring shares and access requests (FR-S4, FR-S5, FR-C12).

TDD: these tests are written before the implementation.

Share expiry (FR-S4):
- A share with an expires_at in the past must no longer grant visibility.
- An active share (no expires_at or future expires_at) grants visibility as before.
- Expired shares must not leak title/content/citation/existence.

Access requests (FR-S5):
- A user can request access to a document they cannot see.
- Owner can approve (grants viewer access + notification) or deny (no leak, no grant).
- Duplicate requests are idempotent.
- Denial does not leak document content.
"""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import (
    AccessRequest,
    Chunk,
    ChunkEmbedding,
    DocPrincipal,
    Document,
    DocumentVersion,
    Folder,
    FolderPrincipal,
    Notification,
    Role,
    Team,
    TeamMember,
    User,
    sessions,
)
from e2eai.documents import (
    create_seeded_document,
    list_documents_view,
    request_access,
    approve_access_request,
    deny_access_request,
    list_access_requests,
    search_documents,
    share_document,
    share_folder,
    visible_chunks,
)
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        out = []
        for text in texts:
            low = text.lower()
            out.append([
                1.0 if "whatsapp" in low or "revenue" in low else 0.0,
                1.0 if "share" in low or "partnership" in low else 0.0,
                1.0 if "team" in low else 0.0,
                1.0 if "secret" in low else 0.0,
            ])
        return out


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


async def _reset(session):
    for model in (AccessRequest, Notification, FolderPrincipal, ChunkEmbedding, DocPrincipal,
                  Chunk, DocumentVersion, Document, Folder, TeamMember, Team):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


# ---------------------------------------------------------------------------
# FR-S4: Share expiry
# ---------------------------------------------------------------------------


def test_expired_share_removes_visibility_from_retrieval_search_list_and_chat():
    """An expired share must not grant visibility for retrieval, search, list views, or chat.
    Non-expired share must still work. Expired share must not leak title/content/citation."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner,
                title="WhatsApp Revenue Partnership Q4",
                text="The WhatsApp revenue share is 30 percent for Q4 partners.",
                page=4,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            authz = RecordingAuthz()

            # Share with Andi — already expired (1 hour ago)
            past = datetime.now(UTC) - timedelta(hours=1)
            await share_document(
                session, authz, actor=owner, document_id=doc.id,
                principal=f"user:{andi.id}", level="viewer", expires_at=past,
            )

            # Andi should NOT see the document (expired share)
            andi_chunks = await visible_chunks(session, await principals(session, andi))
            assert andi_chunks == [], "Expired share must not grant visible_chunks"

            andi_search = await search_documents(session, user=andi, query="WhatsApp")
            assert andi_search == [], "Expired share must not appear in search results"

            andi_list = await list_documents_view(session, user=andi, view="shared_with_me")
            assert andi_list == [], "Expired share must not appear in shared_with_me view"

            andi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=andi, question="WhatsApp revenue"
            )
            assert andi_answer["citations"] == [], "Expired share must not produce citations"
            assert "30 percent" not in andi_answer["answer"], "Expired share must not leak content"
            assert "WhatsApp" not in andi_answer["answer"], "Expired share must not leak title"

            # Share with Budi — expires in 1 hour (still valid)
            future = datetime.now(UTC) + timedelta(hours=1)
            await share_document(
                session, authz, actor=owner, document_id=doc.id,
                principal=f"user:{budi.id}", level="viewer", expires_at=future,
            )

            # Budi SHOULD see the document (non-expired share)
            budi_chunks = await visible_chunks(session, await principals(session, budi))
            assert len(budi_chunks) == 1
            assert budi_chunks[0][0] == "WhatsApp Revenue Partnership Q4"

            budi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=budi, question="WhatsApp revenue"
            )
            assert budi_answer["citations"][0]["document"] == "WhatsApp Revenue Partnership Q4"

    _migrate()
    asyncio.run(run())


def test_no_expiry_share_works_as_before():
    """A share without expires_at (None) grants visibility as before — backward compatible."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Evergreen Doc",
                text="This partnership document has no expiry.", page=1,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            authz = RecordingAuthz()
            await share_document(
                session, authz, actor=owner, document_id=doc.id,
                principal=f"user:{andi.id}", level="viewer",
                # No expires_at — should work as before
            )

            andi_chunks = await visible_chunks(session, await principals(session, andi))
            assert len(andi_chunks) == 1
            assert andi_chunks[0][0] == "Evergreen Doc"

    _migrate()
    asyncio.run(run())


def test_expired_folder_share_removes_inherited_visibility():
    """Expired folder shares must also exclude inherited documents from retrieval."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            folder = Folder(owner_id=owner.id, name="Project Folder", path="/project", created_by=str(owner.id))
            session.add(folder)
            await session.commit()

            doc = await create_seeded_document(
                session, owner=owner, folder=folder,
                title="Project Plan", text="WhatsApp project plan for Q4 team.", page=1,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            authz = RecordingAuthz()
            past = datetime.now(UTC) - timedelta(hours=1)
            await share_folder(
                session, authz, actor=owner, folder_id=folder.id,
                principal=f"user:{andi.id}", level="viewer", expires_at=past,
            )

            andi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=andi, question="WhatsApp project"
            )
            assert andi_answer["citations"] == [], "Expired folder share must not produce citations"
            assert "Project Plan" not in andi_answer["answer"]

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# FR-S5: Access requests
# ---------------------------------------------------------------------------


def test_user_can_request_access_and_owner_approves():
    """A user requests access to a document. Owner approves, granting viewer access + notification."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner,
                title="Restricted Report",
                text="Restricted WhatsApp revenue share details 30 percent.",
                page=2,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            # Andi cannot see the doc before request
            assert await visible_chunks(session, await principals(session, andi)) == []

            # Andi requests access
            req = await request_access(session, requester=andi, document_id=doc.id)
            assert req.status == "pending"
            assert req.document_id == doc.id
            assert req.requester_id == andi.id

            # Owner approves
            authz = RecordingAuthz()
            await approve_access_request(session, authz, owner=owner, request_id=req.id)

            # Refresh request
            await session.refresh(req)
            assert req.status == "approved"

            # Andi can now see the doc
            andi_chunks = await visible_chunks(session, await principals(session, andi))
            assert len(andi_chunks) == 1
            assert andi_chunks[0][0] == "Restricted Report"

            # Notification created for Andi
            notifications = await session.scalars(
                select(Notification).where(Notification.user_id == andi.id, Notification.kind == "access_request.approved")
            )
            notif_list = list(notifications.all())
            assert len(notif_list) == 1
            assert notif_list[0].details["title"] == "Restricted Report"
            # No content leaked in notification
            assert "30 percent" not in str(notif_list[0].details)

    _migrate()
    asyncio.run(run())


def test_owner_denies_access_request_no_leak():
    """Owner denies an access request. No grant, no content leak to the requester."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner,
                title="Confidential Board Minutes",
                text="Secret WhatsApp board minutes with revenue share 50 percent.",
                page=1,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            req = await request_access(session, requester=andi, document_id=doc.id)
            await deny_access_request(session, owner=owner, request_id=req.id)

            await session.refresh(req)
            assert req.status == "denied"

            # Andi still cannot see the doc
            andi_chunks = await visible_chunks(session, await principals(session, andi))
            assert andi_chunks == [], "Denied request must not grant visibility"

            andi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=andi, question="WhatsApp board minutes"
            )
            assert andi_answer["citations"] == [], "Denied request must not produce citations"
            assert "50 percent" not in andi_answer["answer"], "Denied request must not leak content"
            assert "Board Minutes" not in andi_answer["answer"], "Denied request must not leak title"

    _migrate()
    asyncio.run(run())


def test_duplicate_access_request_is_idempotent():
    """A second request for the same document by the same user returns the existing pending request."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Some Doc",
                text="Some content.", page=1,
            )

            req1 = await request_access(session, requester=andi, document_id=doc.id)
            req2 = await request_access(session, requester=andi, document_id=doc.id)
            assert req1.id == req2.id, "Duplicate request should return the same request"
            assert req2.status == "pending"

    _migrate()
    asyncio.run(run())


def test_list_access_requests_scoped_to_owner():
    """Owner can list pending access requests for their documents. Non-owner sees nothing."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Owner Doc",
                text="Owner doc content.", page=1,
            )

            await request_access(session, requester=andi, document_id=doc.id)
            await request_access(session, requester=budi, document_id=doc.id)

            owner_reqs = await list_access_requests(session, owner=owner)
            assert len(owner_reqs) == 2

            # Andi is not the owner — should see no requests to approve
            andi_reqs = await list_access_requests(session, owner=andi)
            assert andi_reqs == []

    _migrate()
    asyncio.run(run())


def test_non_owner_cannot_approve_or_deny():
    """A non-owner cannot approve or deny another owner's document request."""
    async def run():
        from e2eai.core.errors import AppError

        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Owner Only Doc",
                text="Owner only content.", page=1,
            )

            req = await request_access(session, requester=andi, document_id=doc.id)

            # Budi tries to approve — should fail
            try:
                authz = RecordingAuthz()
                await approve_access_request(session, authz, owner=budi, request_id=req.id)
                assert False, "Non-owner should not be able to approve"
            except AppError as e:
                assert e.status == 403

            # Budi tries to deny — should fail
            try:
                await deny_access_request(session, owner=budi, request_id=req.id)
                assert False, "Non-owner should not be able to deny"
            except AppError as e:
                assert e.status == 403

            # Request still pending
            await session.refresh(req)
            assert req.status == "pending"

    _migrate()
    asyncio.run(run())
