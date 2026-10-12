"""FR-I1 data flywheel: flagged answers -> triage queue -> eval/fine-tune dataset -> re-eval -> release.

Deterministic/offline. The queue stores only PII-masked question/correction text (never the answer),
ids, and labels. Triage and export are admin-only and audited.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, Conversation, EvalDataset, EvalRun, Message, MessageFeedback, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    from e2eai.db import FlywheelItem

    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("flywheel.%")))
    await session.execute(delete(FlywheelItem))
    await session.execute(delete(MessageFeedback))
    await session.execute(delete(Message))
    await session.execute(delete(Conversation))
    await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return admin, andi


async def _thumbs_down(session, user, *, question, answer, correction):
    conv = Conversation(user_id=user.id, title="t")
    session.add(conv)
    await session.flush()
    q = Message(conversation_id=conv.id, role="user", content=question)
    session.add(q)
    await session.flush()
    a = Message(conversation_id=conv.id, role="assistant", content=answer)
    session.add(a)
    await session.flush()
    session.add(MessageFeedback(message_id=a.id, rating="down", correction_masked=correction, trace_id="tr-" + str(a.id)[:8]))
    await session.commit()
    return a


def test_collect_thumbs_down_is_idempotent_masked_and_never_stores_answer():
    async def run():
        from e2eai.db import FlywheelItem
        from e2eai.flywheel import collect_from_feedback

        async with sessions()() as session:
            admin, andi = await _reset(session)
            await _thumbs_down(
                session, andi, question="Cuti saya berapa hari? email budi@corp.id", answer="TOPSECRET answer text",
                correction="Cuti tahunan 12 hari",
            )
            created = await collect_from_feedback(session, actor=admin)
            assert created == 1
            assert await collect_from_feedback(session, actor=admin) == 0  # idempotent
            item = await session.scalar(select(FlywheelItem))
            assert item.source == "thumbs_down" and item.status == "queued"
            assert "budi@corp.id" not in item.question_masked and "[EMAIL]" in item.question_masked
            assert item.correction_masked == "Cuti tahunan 12 hari"
            assert "TOPSECRET" not in str(item.__dict__)

            with pytest.raises(AppError) as exc:
                await collect_from_feedback(session, actor=andi)
            assert exc.value.status == 403

    _migrate()
    asyncio.run(run())


def test_flag_manually_validates_source_and_masks():
    async def run():
        from e2eai.flywheel import flag_answer

        async with sessions()() as session:
            admin, andi = await _reset(session)
            item = await flag_answer(
                session, actor=admin, source="low_online_score", question="NIK 3171234567890123 apa?", trace_id="tr-5",
                reason="score 0.2",
            )
            assert item.source == "low_online_score" and "3171234567890123" not in item.question_masked
            with pytest.raises(AppError) as exc:
                await flag_answer(session, actor=admin, source="bogus", question="q")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:
                await flag_answer(session, actor=andi, source="reviewer_flag", question="q")
            assert exc.value.status == 403

    _migrate()
    asyncio.run(run())


def test_triage_export_reeval_release_loop():
    async def run():
        from e2eai.flywheel import (
            export_to_dataset, link_release, link_reeval, triage_item, flag_answer,
        )

        async with sessions()() as session:
            admin, andi = await _reset(session)
            a = await flag_answer(session, actor=admin, source="reviewer_flag", question="Berapa cuti?", correction="12 hari")
            b = await flag_answer(session, actor=admin, source="reviewer_flag", question="Jam kerja?")  # no correction
            c = await flag_answer(session, actor=admin, source="reviewer_flag", question="Spam")

            with pytest.raises(AppError) as exc:  # non-admin cannot triage
                await triage_item(session, actor=andi, item_id=a.id, decision="accept", target="eval")
            assert exc.value.status == 403
            with pytest.raises(AppError) as exc:  # accepting needs a correction (expected answer)
                await triage_item(session, actor=admin, item_id=b.id, decision="accept", target="eval")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:  # unknown target
                await triage_item(session, actor=admin, item_id=a.id, decision="accept", target="weights")
            assert exc.value.status == 400
            await triage_item(session, actor=admin, item_id=c.id, decision="dismiss")
            await triage_item(session, actor=admin, item_id=a.id, decision="accept", target="eval")

            with pytest.raises(AppError) as exc:  # nothing to export for the finetune target
                await export_to_dataset(session, actor=admin, target="finetune", name="flywheel-ft")
            assert exc.value.status == 409
            ds = await export_to_dataset(session, actor=admin, target="eval", name="flywheel-eval")
            assert isinstance(ds, EvalDataset) and ds.source == "flywheel" and len(ds.items) == 1
            item = ds.items[0]
            assert item["question"] == "Berapa cuti?" and item["expected_answer"] == "12 hari"
            assert item["annotation"]["splits"] == ["gold"]

            await session.refresh(a)
            assert a.status == "exported" and a.dataset_id == ds.id

            run_row = EvalRun(dataset_id=ds.id, adapter="ragas.local", status="completed", metrics={"score": 0.9}, item_results=[])
            session.add(run_row)
            await session.commit()
            await link_reeval(session, actor=admin, item_id=a.id, run_id=run_row.id)
            with pytest.raises(AppError) as exc:  # release needs a ref
                await link_release(session, actor=admin, item_id=a.id, release_ref=" ")
            assert exc.value.status == 400
            done = await link_release(session, actor=admin, item_id=a.id, release_ref="hr-bot@v8")
            assert done.status == "released" and done.release_ref == "hr-bot@v8"

            with pytest.raises(AppError) as exc:  # cannot re-triage a released item
                await triage_item(session, actor=admin, item_id=a.id, decision="dismiss")
            assert exc.value.status == 409

            actions = set((await session.scalars(select(AuditEntry.action).where(AuditEntry.action.like("flywheel.%")))).all())
            assert {"flywheel.flag", "flywheel.triage", "flywheel.export", "flywheel.reeval", "flywheel.release"} <= actions

    _migrate()
    asyncio.run(run())


def test_finetune_target_uses_finetuning_split_and_summary_counts():
    async def run():
        from e2eai.flywheel import export_to_dataset, flag_answer, queue_summary, triage_item

        async with sessions()() as session:
            admin, _ = await _reset(session)
            x = await flag_answer(session, actor=admin, source="reviewer_flag", question="Q1", correction="A1")
            await flag_answer(session, actor=admin, source="reviewer_flag", question="Q2")
            await triage_item(session, actor=admin, item_id=x.id, decision="accept", target="finetune")
            summary = await queue_summary(session, actor=admin)
            assert summary["by_status"] == {"accepted": 1, "queued": 1}
            ds = await export_to_dataset(session, actor=admin, target="finetune", name="flywheel-ft")
            assert ds.items[0]["annotation"]["splits"] == ["fine_tuning"]

    _migrate()
    asyncio.run(run())


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    for p in (
        "/api/v1/improve/flywheel/collect", "/api/v1/improve/flywheel/flag", "/api/v1/improve/flywheel/export",
        "/api/v1/improve/flywheel/{item_id}/triage", "/api/v1/improve/flywheel/{item_id}/reeval",
        "/api/v1/improve/flywheel/{item_id}/release",
    ):
        assert "post" in paths[p], p
    assert "get" in paths["/api/v1/improve/flywheel"]
