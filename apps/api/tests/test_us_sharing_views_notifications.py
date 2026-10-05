"""P0 sharing completion: group principals, folder inheritance, views, notifications, chat scopes.

TDD: these tests were written before the implementation for FR-S1/FR-S2/FR-S3/FR-S6/FR-C3/FR-C10.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import (
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
    list_notifications,
    revoke_folder,
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
                1.0 if "team" in low else 0.0,
                1.0 if "division" in low else 0.0,
                1.0 if "role" in low else 0.0,
                1.0 if "whatsapp" in low or "share" in low else 0.0,
            ])
        return out


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


async def _reset(session):
    for model in (Notification, FolderPrincipal, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder, TeamMember, Team):
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


def test_group_principal_shares_work_without_embedding_copies_or_budi_leak():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            team = Team(division_id=andi.division_id, name="Sales AI")
            session.add(team)
            await session.flush()
            session.add(TeamMember(team_id=team.id, user_id=andi.id))
            await session.commit()

            doc = await create_seeded_document(session, owner=owner, title="Team Playbook", text="Team share says pipeline discount is 12 percent.", page=2)
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
            before_embeddings = await session.scalar(select(func.count()).select_from(ChunkEmbedding))

            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id, principal=f"team:{team.id}", level="viewer")

            assert authz.calls[0]["writes"] == [{"user": f"team:{team.id}", "relation": "viewer", "object": f"document:{doc.id}"}]
            assert await session.scalar(select(func.count()).select_from(ChunkEmbedding)) == before_embeddings
            assert "Team Playbook" in [row[0] for row in await visible_chunks(session, await principals(session, andi))]
            assert await visible_chunks(session, await principals(session, budi)) == []

    _migrate()
    asyncio.run(run())


def test_division_role_and_org_shares_use_principals_without_leaking_unrelated_divisions():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            role = await session.scalar(select(Role).where(Role.name == "business_user"))
            assert role is not None
            authz = RecordingAuthz()

            division_doc = await create_seeded_document(session, owner=owner, title="Sales Division Brief", text="division-only quota")
            await share_document(session, authz, actor=owner, document_id=division_doc.id, principal=f"division:{andi.division_id}")
            assert "Sales Division Brief" in [row[0] for row in await visible_chunks(session, await principals(session, andi))]
            assert "Sales Division Brief" not in [row[0] for row in await visible_chunks(session, await principals(session, budi))]

            role_doc = await create_seeded_document(session, owner=owner, title="Role Brief", text="role-based note")
            await share_document(session, authz, actor=owner, document_id=role_doc.id, principal=f"role:{role.id}")
            assert "Role Brief" in [row[0] for row in await visible_chunks(session, await principals(session, budi))]

            org_doc = await create_seeded_document(session, owner=owner, title="Company Brief", text="company-wide note")
            await share_document(session, authz, actor=owner, document_id=org_doc.id, principal=f"org:{owner.org_id}")
            assert "Company Brief" in [row[0] for row in await visible_chunks(session, await principals(session, budi))]
            assert authz.calls[-1]["writes"] == [{"user": f"org:{owner.org_id}", "relation": "viewer", "object": f"document:{org_doc.id}"}]

    _migrate()
    asyncio.run(run())


def test_folder_share_inherits_to_contents_and_revoke_tightens_next_query():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            folder = Folder(owner_id=owner.id, name="Sales Folder", path="/sales", created_by=str(owner.id))
            session.add(folder)
            await session.commit()
            doc = await create_seeded_document(session, owner=owner, folder=folder, title="Folder Plan", text="Folder inherited share contains the WhatsApp renewal plan.", page=4)
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            authz = RecordingAuthz()
            await share_folder(session, authz, actor=owner, folder_id=folder.id, principal=f"user:{andi.id}", level="viewer")
            answer = await answer_question(session, embedder=FakeEmbedder(), user=andi, question="WhatsApp renewal")
            assert answer["citations"][0]["document"] == "Folder Plan"

            await revoke_folder(session, authz, actor=owner, folder_id=folder.id, principal=f"user:{andi.id}")
            after = await answer_question(session, embedder=FakeEmbedder(), user=andi, question="WhatsApp renewal")
            assert after["citations"] == []
            assert "Folder Plan" not in after["answer"]
            assert authz.calls[-1]["deletes"] == [{"user": f"user:{andi.id}", "relation": "viewer", "object": f"folder:{folder.id}"}]

    _migrate()
    asyncio.run(run())


def test_shared_views_and_notifications_are_permission_scoped_and_safe():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            owner_doc = await create_seeded_document(session, owner=owner, title="Owner Only", text="owner private text")
            shared_doc = await create_seeded_document(session, owner=owner, title="Shared Brief", text="shared safe text")
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=shared_doc.id, principal=f"user:{andi.id}", level="viewer")

            assert [d["title"] for d in await list_documents_view(session, user=owner, view="my_documents")] == ["Owner Only", "Shared Brief"]
            assert [d["title"] for d in await list_documents_view(session, user=andi, view="shared_with_me")] == ["Shared Brief"]
            assert await list_documents_view(session, user=budi, view="shared_with_me") == []

            andi_notifications = await list_notifications(session, user=andi)
            assert len(andi_notifications) == 1
            assert andi_notifications[0].kind == "document.shared"
            assert andi_notifications[0].details["title"] == "Shared Brief"
            assert "shared safe text" not in str(andi_notifications[0].details)
            assert await list_notifications(session, user=budi) == []

    _migrate()
    asyncio.run(run())


def test_chat_scope_narrows_retrieval_and_cannot_force_unpermitted_document():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            owned = await create_seeded_document(session, owner=andi, title="Andi Owned", text="WhatsApp owned answer is blue.")
            shared = await create_seeded_document(session, owner=owner, title="Shared WhatsApp", text="WhatsApp shared answer is green.")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=owned.id)
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=shared.id)
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=shared.id, principal=f"user:{andi.id}")

            shared_only = await answer_question(session, embedder=FakeEmbedder(), user=andi, question="WhatsApp", scope="shared_with_me")
            assert shared_only["citations"][0]["document"] == "Shared WhatsApp"

            this_doc = await answer_question(session, embedder=FakeEmbedder(), user=andi, question="WhatsApp", scope="this_document", document_id=owned.id)
            assert this_doc["citations"][0]["document"] == "Andi Owned"

            forced = await answer_question(session, embedder=FakeEmbedder(), user=budi, question="WhatsApp", scope="this_document", document_id=shared.id)
            assert forced["citations"] == []
            assert "Shared WhatsApp" not in forced["answer"]
            assert "green" not in forced["answer"]

    _migrate()
    asyncio.run(run())
