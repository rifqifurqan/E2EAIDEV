"""P0 Eval Lab: datasets, synthetic data, adapter boundary, permission-leak suite, run comparison."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, EvalDataset, EvalRun, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.eval_lab import (
    LocalRagasAdapter,
    compare_runs,
    create_dataset,
    generate_synthetic_qa,
    run_evaluation,
    run_permission_leak_suite,
)
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
                1.0 if "leave" in low else 0.0,
                1.0 if "secret" in low or "forbidden" in low else 0.0,
            ])
        return out


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


async def _reset(session):
    for model in (EvalRun, EvalDataset, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
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


def test_dataset_versioning_and_synthetic_generation_are_deterministic_and_safe():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            items = generate_synthetic_qa(
                [{"title": "WhatsApp Partnership", "text": "Revenue share is 30 percent.", "page": 4}],
                personas=["Andi Sales", "Budi HR"],
                adversarial=True,
            )
            ds1 = await create_dataset(session, name="permission-smoke", items=items, source="synthetic", created_by=f"user:{owner.id}")
            ds2 = await create_dataset(session, name="permission-smoke", items=items[:1], source="synthetic", created_by=f"user:{owner.id}")

            assert ds1.version == 1
            assert ds2.version == 2
            assert {item["kind"] for item in ds1.items} == {"qa", "adversarial"}
            assert all("answer" in item and "question" in item and "persona" in item for item in ds1.items)
            assert "30 percent" in ds1.items[0]["answer"]

    _migrate()
    asyncio.run(run())


def test_ragas_adapter_boundary_records_metrics_and_run_comparison_flags_regression():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            ds = await create_dataset(
                session,
                name="ragas-smoke",
                items=[
                    {"question": "What is revenue share?", "answer": "30 percent", "expected_answer": "30 percent", "kind": "qa"},
                    {"question": "Unknown?", "answer": "I don't know", "expected_answer": "12 days", "kind": "qa"},
                ],
                source="manual",
                created_by=f"user:{owner.id}",
            )
            good = await run_evaluation(session, dataset_id=ds.id, adapter=LocalRagasAdapter(score_override=0.9), created_by=f"user:{owner.id}")
            bad = await run_evaluation(session, dataset_id=ds.id, adapter=LocalRagasAdapter(score_override=0.4), created_by=f"user:{owner.id}")

            assert good.adapter == "ragas.local"
            assert good.metrics["answer_correctness"] == 0.9
            assert good.metrics["items"] == 2
            comparison = compare_runs(good, bad, threshold=0.1)
            assert comparison["regression"] is True
            assert comparison["delta"]["answer_correctness"] == -0.5

    _migrate()
    asyncio.run(run())


def test_permission_leak_suite_records_zero_leaks_without_revealing_restricted_title():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            doc = await create_seeded_document(
                session,
                owner=owner,
                title="WhatsApp Secret Partnership",
                text="WhatsApp forbidden revenue share is 30 percent.",
                page=4,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            run = await run_permission_leak_suite(
                session,
                name="permission-leak-smoke",
                embedder=FakeEmbedder(),
                personas=[
                    {"user": andi, "question": "What is the WhatsApp revenue share?", "forbidden_terms": []},
                    {"user": budi, "question": "What is the WhatsApp revenue share?", "forbidden_terms": ["WhatsApp Secret Partnership", "30 percent", "forbidden"]},
                ],
                created_by="test",
            )

            assert run.metrics["leaks"] == 0
            assert run.metrics["probes"] == 2
            assert run.item_results[1]["leaked"] is False
            assert "WhatsApp Secret Partnership" not in str(run.item_results[1])
            assert "30 percent" not in str(run.item_results[1])

    _migrate()
    asyncio.run(run())
