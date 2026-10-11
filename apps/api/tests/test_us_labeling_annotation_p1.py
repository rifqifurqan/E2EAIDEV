"""FR-D11 Labeling and annotation for gold sets and fine-tuning data."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import EvalDataset, EvalRun, User, sessions
from e2eai.eval_lab import annotate_dataset_items, build_annotation_export, create_dataset
from e2eai.seed import seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    for model in (EvalRun, EvalDataset):
        await session.execute(delete(model))
    await session.commit()


async def _owner(session):
    await seed_demo(session, password="TestPassword_123456789")
    return await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))


def test_dataset_annotations_create_versioned_gold_and_finetuning_slice_without_raw_content_in_export():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _owner(session)
            ds = await create_dataset(
                session,
                name="support-goldset",
                source="manual",
                created_by=f"user:{owner.id}",
                items=[
                    {
                        "item_id": "case-1",
                        "question": "What is the confidential WhatsApp revenue share?",
                        "answer": "Revenue share is 30 percent.",
                        "expected_answer": "30 percent",
                    },
                    {
                        "item_id": "case-2",
                        "question": "How many leave days does Andi have?",
                        "answer": "12 days.",
                        "expected_answer": "12 days",
                    },
                ],
            )

            annotated = await annotate_dataset_items(
                session,
                dataset_id=ds.id,
                annotations=[
                    {
                        "item_id": "case-1",
                        "labels": ["permission-leak", "gold"],
                        "splits": ["gold"],
                        "quality": "accepted",
                    },
                    {
                        "index": 1,
                        "labels": ["fine-tuning", "needs-rewrite"],
                        "splits": ["fine_tuning"],
                        "quality": "needs_fix",
                    },
                ],
                created_by=f"user:{owner.id}",
                reviewer_id=str(owner.id),
            )
            export = build_annotation_export(annotated)

            assert annotated.id != ds.id
            assert annotated.name == ds.name
            assert annotated.version == 2
            assert annotated.source == "annotation"
            assert annotated.items[0]["annotation"] == {
                "labels": ["gold", "permission-leak"],
                "splits": ["gold"],
                "quality": "accepted",
                "reviewer_id": str(owner.id),
            }
            assert annotated.items[1]["annotation"]["splits"] == ["fine_tuning"]

            assert export["kind"] == "dataset_annotation_export"
            assert export["dataset"] == {"id": str(annotated.id), "name": "support-goldset", "version": 2}
            assert export["counts"] == {"items": 2, "annotated": 2, "gold": 1, "fine_tuning": 1}
            assert export["label_counts"] == {"fine-tuning": 1, "gold": 1, "needs-rewrite": 1, "permission-leak": 1}
            assert {row["item_id"] for row in export["items"]} == {"case-1", "case-2"}
            serialized = str(export)
            assert "confidential" not in serialized
            assert "Revenue share" not in serialized
            assert "12 days" not in serialized

    _migrate()
    asyncio.run(run())


def test_annotation_rejects_unknown_items_and_invalid_labels_before_writing_new_version():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _owner(session)
            ds = await create_dataset(
                session,
                name="reject-annotations",
                source="manual",
                created_by=f"user:{owner.id}",
                items=[{"item_id": "known", "question": "Q", "answer": "A"}],
            )

            for bad_annotation in (
                {"item_id": "missing", "labels": ["gold"], "splits": ["gold"], "quality": "accepted"},
                {"item_id": "known", "labels": ["Not Safe!"], "splits": ["gold"], "quality": "accepted"},
            ):
                try:
                    await annotate_dataset_items(
                        session,
                        dataset_id=ds.id,
                        annotations=[bad_annotation],
                        created_by=f"user:{owner.id}",
                        reviewer_id=str(owner.id),
                    )
                except Exception:
                    await session.rollback()
                else:
                    raise AssertionError("invalid annotation was accepted")

            versions = await session.scalars(select(EvalDataset.version).where(EvalDataset.name == "reject-annotations").order_by(EvalDataset.version))
            assert list(versions) == [1]

    _migrate()
    asyncio.run(run())
