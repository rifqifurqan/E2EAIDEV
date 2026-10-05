"""P0 release bundle and bot access/scope intersection (FR-RL1, FR-RL5, FR-RL7)."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.bot_release import (
    answer_bot_question,
    create_bot,
    grant_bot_access,
    release_bundle,
    rollback_bundle,
    set_bot_scope,
)
from e2eai.db import (
    Bot,
    BotBundle,
    BotGrant,
    BotScope,
    Chunk,
    ChunkEmbedding,
    DocPrincipal,
    Document,
    DocumentVersion,
    Folder,
    Team,
    TeamMember,
    User,
    sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import index_document_chunks
from e2eai.seed import seed_demo


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        out = []
        for text in texts:
            low = text.lower()
            out.append([
                1.0 if "whatsapp" in low else 0.0,
                1.0 if "hr" in low else 0.0,
                1.0 if "secret" in low or "andi" in low else 0.0,
            ])
        return out


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


async def _reset(session):
    for model in (BotScope, BotGrant, BotBundle, Bot, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder, TeamMember, Team):
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


def test_release_bundle_versions_and_rollback_switches_production_pointer():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            bot = await create_bot(session, owner=owner, name="Sales Bot")
            v1 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1", "model": "qwen", "index": "idx1", "reranker": "none"})
            v2 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v2", "model": "qwen", "index": "idx1", "reranker": "none"})

            assert v1.version == 1
            assert v1.status == "superseded"
            assert v2.version == 2
            assert v2.status == "production"
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == v2.id

            rolled = await rollback_bundle(session, actor=owner, bot_id=bot.id, target_bundle_id=v1.id)
            assert rolled.id == v1.id
            assert rolled.status == "production"
            v2_after = await session.get(BotBundle, v2.id)
            assert v2_after.status == "rolled_back"
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == v1.id

    _migrate()
    asyncio.run(run())


def test_bot_access_grants_support_team_principal_without_authorizing_unrelated_user():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            team = Team(division_id=andi.division_id, name="Sales Bot Users")
            session.add(team)
            await session.flush()
            session.add(TeamMember(team_id=team.id, user_id=andi.id))
            await session.commit()
            bot = await create_bot(session, owner=owner, name="Sales Bot")
            await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            await grant_bot_access(session, actor=owner, bot_id=bot.id, principal=f"team:{team.id}")

            assert await answer_bot_question(session, embedder=FakeEmbedder(), user=budi, bot_id=bot.id, question="WhatsApp") == {
                "answer": "I don't have access to that bot.",
                "citations": [],
            }

    _migrate()
    asyncio.run(run())


def test_bot_scope_intersects_with_user_permissions_and_never_widens_access():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            public_doc = await create_seeded_document(session, owner=owner, title="Shared WhatsApp", text="WhatsApp shared policy is green.")
            andi_doc = await create_seeded_document(session, owner=owner, title="Andi Secret Scope", text="WhatsApp Andi secret is red.")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=public_doc.id)
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=andi_doc.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=public_doc.id, principal=f"user:{andi.id}")
            await share_document(session, RecordingAuthz(), actor=owner, document_id=public_doc.id, principal=f"user:{budi.id}")
            await share_document(session, RecordingAuthz(), actor=owner, document_id=andi_doc.id, principal=f"user:{andi.id}")

            bot = await create_bot(session, owner=owner, name="Scoped Bot")
            await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            await grant_bot_access(session, actor=owner, bot_id=bot.id, principal=f"org:{owner.org_id}")
            await set_bot_scope(session, actor=owner, bot_id=bot.id, document_ids=[public_doc.id, andi_doc.id])

            andi_answer = await answer_bot_question(session, embedder=FakeEmbedder(), user=andi, bot_id=bot.id, question="WhatsApp")
            assert andi_answer["citations"][0]["document"] in {"Shared WhatsApp", "Andi Secret Scope"}

            budi_answer = await answer_bot_question(session, embedder=FakeEmbedder(), user=budi, bot_id=bot.id, question="WhatsApp")
            assert budi_answer["citations"][0]["document"] == "Shared WhatsApp"
            assert "Andi Secret Scope" not in str(budi_answer)
            assert "Andi secret" not in str(budi_answer)
            assert "secret is red" not in str(budi_answer)

    _migrate()
    asyncio.run(run())


def test_bot_scope_can_narrow_to_one_permitted_document():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            scoped = await create_seeded_document(session, owner=owner, title="Scoped HR", text="HR scoped answer is twelve days.")
            outside = await create_seeded_document(session, owner=owner, title="Outside WhatsApp", text="WhatsApp outside answer should not appear.")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=scoped.id)
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=outside.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=scoped.id, principal=f"user:{andi.id}")
            await share_document(session, RecordingAuthz(), actor=owner, document_id=outside.id, principal=f"user:{andi.id}")
            bot = await create_bot(session, owner=owner, name="Narrow Bot")
            await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            await grant_bot_access(session, actor=owner, bot_id=bot.id, principal=f"user:{andi.id}")
            await set_bot_scope(session, actor=owner, bot_id=bot.id, document_ids=[scoped.id])

            answer = await answer_bot_question(session, embedder=FakeEmbedder(), user=andi, bot_id=bot.id, question="WhatsApp HR")
            assert answer["citations"][0]["document"] == "Scoped HR"
            assert "Outside WhatsApp" not in str(answer)
            assert "outside answer" not in str(answer)

    _migrate()
    asyncio.run(run())
