"""FR-C6 Derived content inherits strictest permissions of sources."""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from e2eai.db import (
    Chunk,
    DocPrincipal,
    Document,
    DocumentVersion,
    EvalDataset,
    FolderPrincipal,
    User,
    sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.derived_permissions import compute_derived_permissions, inherit_strictest
from e2eai.seed import seed_demo


async def _reset(session):
    for model in (Chunk, DocPrincipal, FolderPrincipal, DocumentVersion, Document, FolderPrincipal, EvalDataset):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    from sqlalchemy import func, select
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


def test_inherit_strictest_picks_most_restrictive_level_and_never_widens_across_sources():
    strictest = inherit_strictest([
        {"principal": "viewer", "level": "editor"},
        {"principal": "team:eng", "level": "viewer"},
        {"principal": "user:123", "level": "owner"},
    ])
    assert strictest == "viewer"


def test_inherit_strictest_rejects_unknown_levels_and_deduplicates_principals():
    strictest = inherit_strictest([
        {"principal": "viewer", "level": "viewer"},
        {"principal": "viewer", "level": "owner"},
    ])
    assert strictest == "viewer"


def test_compute_derived_permissions_inherits_strictest_from_multiple_sources():
    perms = compute_derived_permissions(
        source_ids=["doc:A", "doc:B"],
        source_levels={
            "doc:A": [{"principal": "viewer", "level": "editor"}, {"principal": "team:eng", "level": "viewer"}],
            "doc:B": [{"principal": "viewer", "level": "owner"}],
        },
    )
    assert perms["sources"] == ["doc:A", "doc:B"]
    assert perms["effective_level"] == "viewer"
    assert "user:" not in str(perms["granted_principals"])


def test_derived_dataset_permissions_never_expand_to_individual_users():
    dataset_items = [
        {"item_id": "d1", "source_document_id": "doc-A", "source_level": "viewer"},
        {"item_id": "d2", "source_document_id": "doc-B", "source_level": "editor"},
    ]
    perms = compute_derived_permissions(
        source_ids=["doc-A", "doc-B"],
        source_levels={
            "doc-A": [{"principal": "user:secret-budi", "level": "viewer"}],
            "doc-B": [{"principal": "team:sales", "level": "editor"}],
        },
    )
    assert perms["effective_level"] == "viewer"
    assert perms["granted_principals"] == ["team:sales"]
    assert "secret-budi" not in str(perms)
