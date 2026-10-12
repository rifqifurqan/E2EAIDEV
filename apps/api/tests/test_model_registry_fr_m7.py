"""FR-M7 model registry with lineage, eval scores, and approval status.

Versioned model entries record lineage (base model / parent version / source / dataset reference),
eval scores copied from existing EvalRun metrics, and an admin-controlled approval status.
Approval requires at least one eval score. Cards/lineage are secret-safe.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, EvalDataset, EvalRun, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    from e2eai.db import ModelRegistryEntry

    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("model_registry.%")))
    await session.execute(delete(ModelRegistryEntry))
    await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    engineer = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return admin, engineer


def test_register_versions_with_lineage_and_safe_metadata():
    async def run():
        from e2eai.model_registry import get_lineage_chain, register_model_version

        async with sessions()() as session:
            admin, eng = await _people(session)
            v1 = await register_model_version(
                session, actor=eng, name="support-chat", version="1.0",
                lineage={"base_model": "qwen3:4b", "source": "ollama", "api_key": "sk-abc", "note": "token=abc123"},
            )
            assert v1.approval_status == "pending"
            assert "api_key" not in v1.lineage
            assert v1.lineage["note"] == "[redacted]"
            assert v1.lineage["base_model"] == "qwen3:4b"

            v2 = await register_model_version(
                session, actor=eng, name="support-chat", version="1.1", parent_version="1.0",
                lineage={"base_model": "qwen3:4b", "source": "fine-tune", "dataset": "gold-set@3"},
            )
            chain = await get_lineage_chain(session, name="support-chat", version="1.1")
            assert [c["version"] for c in chain] == ["1.1", "1.0"]
            assert v2.parent_version == "1.0"

            with pytest.raises(AppError) as exc:  # duplicate name+version
                await register_model_version(session, actor=eng, name="support-chat", version="1.0")
            assert exc.value.status == 409
            with pytest.raises(AppError) as exc:  # unknown parent
                await register_model_version(session, actor=eng, name="support-chat", version="2.0", parent_version="9.9")
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())


def test_eval_scores_from_runs_and_approval_requires_scores_and_admin():
    async def run():
        from e2eai.model_registry import attach_eval_run, decide_approval, register_model_version

        async with sessions()() as session:
            admin, eng = await _people(session)
            ds = EvalDataset(name="gold", version=1, source="manual", items=[], created_by="test")
            session.add(ds)
            await session.flush()
            run_row = EvalRun(
                dataset_id=ds.id, adapter="ragas.local", status="completed",
                metrics={"faithfulness": 0.91, "answer_relevance": 0.88, "label": "text", "ok": True}, item_results=[],
            )
            session.add(run_row)
            await session.commit()

            entry = await register_model_version(session, actor=eng, name="m", version="1")
            with pytest.raises(AppError) as exc:  # no scores yet
                await decide_approval(session, actor=admin, name="m", version="1", decision="approved")
            assert exc.value.status == 409

            entry = await attach_eval_run(session, actor=eng, name="m", version="1", run_id=run_row.id)
            assert entry.eval_scores[str(run_row.id)]["adapter"] == "ragas.local"
            assert entry.eval_scores[str(run_row.id)]["metrics"] == {"faithfulness": 0.91, "answer_relevance": 0.88}

            with pytest.raises(AppError) as exc:  # engineer cannot approve
                await decide_approval(session, actor=eng, name="m", version="1", decision="approved")
            assert exc.value.status == 403
            with pytest.raises(AppError) as exc:
                await decide_approval(session, actor=admin, name="m", version="1", decision="maybe")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:  # unknown run
                import uuid
                await attach_eval_run(session, actor=eng, name="m", version="1", run_id=uuid.uuid4())
            assert exc.value.status == 404

            approved = await decide_approval(session, actor=admin, name="m", version="1", decision="approved")
            assert approved.approval_status == "approved"
            assert approved.approved_by == str(admin.id)

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.like("model_registry.%")).order_by(AuditEntry.seq)
            )).scalars().all()
            assert [a.action for a in audits] == [
                "model_registry.register", "model_registry.eval_attached", "model_registry.decide",
            ]
            for a in audits:
                assert "sk-" not in str(a.details) and "faithfulness" not in str(a.details)

    _migrate()
    asyncio.run(run())


def test_list_registry_and_routes_are_wired():
    async def run():
        from e2eai.model_registry import list_models, register_model_version

        async with sessions()() as session:
            admin, eng = await _people(session)
            await register_model_version(session, actor=eng, name="a", version="1")
            await register_model_version(session, actor=eng, name="a", version="2")
            await register_model_version(session, actor=eng, name="b", version="1")
            rows = await list_models(session)
            assert [(r["name"], r["version"]) for r in rows] == [("a", "1"), ("a", "2"), ("b", "1")]
            assert {r["approval_status"] for r in rows} == {"pending"}
            assert [r["name"] for r in await list_models(session, name="b")] == ["b"]

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/model-registry"] and "post" in paths["/api/v1/model-registry"]
    assert "post" in paths["/api/v1/model-registry/{name}/{version}/eval-runs"]
    assert "post" in paths["/api/v1/model-registry/{name}/{version}/decision"]
    assert "get" in paths["/api/v1/model-registry/{name}/{version}/lineage"]
