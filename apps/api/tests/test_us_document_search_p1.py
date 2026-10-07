"""Permission-filtered document search (FR-S10, FR-C12).

TDD tests — written before the implementation. Each test proves a specific invariant:
- Owner finds own document by title and by chunk content
- Shared user finds a shared document
- Unshared user gets empty results and no title/snippet leak (FR-C12)
- Folder/team/role/division/org inherited access participates in search
- Filters (sensitivity, status, view) narrow but never widen results
- Revoke removes result immediately from search
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
    revoke_document,
    search_documents,
    share_document,
    share_folder,
    trash_document,
    update_sensitivity,
)
from e2eai.seed import seed_demo


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


# ---------------------------------------------------------------------------
# 1. Owner can find own document by title and by content/chunk text
# ---------------------------------------------------------------------------
def test_owner_finds_own_doc_by_title_and_content():
    """FR-S10: owner's documents appear in search by title match and by chunk text match."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="Quarterly Sales Report",
                text="Revenue grew 15 percent in Q3 driven by enterprise deals.",
            )

            # Search by title keyword
            by_title = await search_documents(session, user=owner, query="Quarterly")
            assert len(by_title) >= 1
            hit = next(r for r in by_title if r["document_id"] == str(doc.id))
            assert hit["title"] == "Quarterly Sales Report"
            assert hit["match_kind"] == "title"
            assert hit["sensitivity"] == "internal"
            assert hit["status"] == "active"
            assert hit["owner_id"] == str(owner.id)
            # No snippet/content field leaked
            assert "text" not in hit
            assert "snippet" not in hit
            assert "content" not in hit

            # Search by chunk content keyword
            by_content = await search_documents(session, user=owner, query="enterprise deals")
            assert len(by_content) >= 1
            content_hit = next(r for r in by_content if r["document_id"] == str(doc.id))
            assert content_hit["match_kind"] == "content"
            assert content_hit["title"] == "Quarterly Sales Report"

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Shared user can find a shared document
# ---------------------------------------------------------------------------
def test_shared_user_finds_shared_document():
    """FR-S10: a direct user share makes the document searchable by the grantee."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="Shared Roadmap",
                text="Product roadmap for H2 includes new API features.",
            )
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id,
                                 principal=f"user:{andi.id}", level="viewer")

            results = await search_documents(session, user=andi, query="Roadmap")
            assert len(results) == 1
            assert results[0]["document_id"] == str(doc.id)
            assert results[0]["title"] == "Shared Roadmap"

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 3. Unshared user gets empty results and no title/snippet leak (FR-C12)
# ---------------------------------------------------------------------------
def test_unshared_user_gets_empty_and_no_leak():
    """FR-S10 + FR-C12: searching the exact title or content of a restricted document returns
    nothing for an unauthorized user. No title, no snippet, no existence hint."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="Confidential Merger Plan",
                text="Target company valuation is 500 million dollars.",
            )

            # Budi searches the exact title
            by_title = await search_documents(session, user=budi, query="Confidential Merger Plan")
            assert by_title == []

            # Budi searches exact content
            by_content = await search_documents(session, user=budi, query="500 million dollars")
            assert by_content == []

            # Verify no field in any result leaks the title or content
            broad = await search_documents(session, user=budi, query="Merger")
            for r in broad:
                assert "Confidential" not in str(r)
                assert "500 million" not in str(r)

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. Folder/team/role/division/org inherited access participates in search
# ---------------------------------------------------------------------------
def test_inherited_access_team_folder_division_role_org():
    """FR-S10 + FR-S2/FR-S3: group principals and folder shares make docs searchable."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            authz = RecordingAuthz()

            # --- Team share ---
            team = Team(division_id=andi.division_id, name="Sales AI")
            session.add(team)
            await session.flush()
            session.add(TeamMember(team_id=team.id, user_id=andi.id))
            await session.commit()

            team_doc = await create_seeded_document(
                session, owner=owner, title="Team Playbook Search",
                text="Team pipeline discount is 12 percent.",
            )
            await share_document(session, authz, actor=owner, document_id=team_doc.id,
                                 principal=f"team:{team.id}", level="viewer")
            assert len(await search_documents(session, user=andi, query="Playbook Search")) == 1
            assert await search_documents(session, user=budi, query="Playbook Search") == []

            # --- Folder share ---
            folder = Folder(owner_id=owner.id, name="Shared Folder", path="/shared", created_by=str(owner.id))
            session.add(folder)
            await session.commit()
            folder_doc = await create_seeded_document(
                session, owner=owner, folder=folder, title="Folder Doc Search",
                text="Folder inherited plan details.",
            )
            await share_folder(session, authz, actor=owner, folder_id=folder.id,
                               principal=f"user:{andi.id}", level="viewer")
            assert len(await search_documents(session, user=andi, query="Folder Doc Search")) == 1
            assert await search_documents(session, user=budi, query="Folder Doc Search") == []

            # --- Division share ---
            division_doc = await create_seeded_document(
                session, owner=owner, title="Division Brief Search",
                text="Division-only quota info.",
            )
            await share_document(session, authz, actor=owner, document_id=division_doc.id,
                                 principal=f"division:{andi.division_id}")
            assert len(await search_documents(session, user=andi, query="Division Brief Search")) == 1
            # Budi is in HR division, not Sales — should not see it
            assert await search_documents(session, user=budi, query="Division Brief Search") == []

            # --- Role share ---
            role = await session.scalar(select(Role).where(Role.name == "business_user"))
            role_doc = await create_seeded_document(
                session, owner=owner, title="Role Brief Search",
                text="Role-based note content.",
            )
            await share_document(session, authz, actor=owner, document_id=role_doc.id,
                                 principal=f"role:{role.id}")
            # Both andi and budi have business_user role
            assert len(await search_documents(session, user=andi, query="Role Brief Search")) == 1
            assert len(await search_documents(session, user=budi, query="Role Brief Search")) == 1

            # --- Org share ---
            org_doc = await create_seeded_document(
                session, owner=owner, title="Company Brief Search",
                text="Company-wide announcement.",
            )
            await share_document(session, authz, actor=owner, document_id=org_doc.id,
                                 principal=f"org:{owner.org_id}")
            assert len(await search_documents(session, user=andi, query="Company Brief Search")) == 1
            assert len(await search_documents(session, user=budi, query="Company Brief Search")) == 1

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 5. Filters (sensitivity/status/view) narrow but never widen
# ---------------------------------------------------------------------------
def test_filters_narrow_never_widen():
    """FR-S10: sensitivity, status, and view filters narrow the already-permission-filtered set."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            authz = RecordingAuthz()

            pub_doc = await create_seeded_document(
                session, owner=owner, title="Public Announcement",
                text="Public text about the company event.",
            )
            await update_sensitivity(session, actor=owner, document_id=pub_doc.id, sensitivity="public")

            conf_doc = await create_seeded_document(
                session, owner=owner, title="Confidential Report",
                text="Confidential financial projections.",
            )
            await update_sensitivity(session, actor=owner, document_id=conf_doc.id, sensitivity="confidential")

            # Share both with Andi
            await share_document(session, authz, actor=owner, document_id=pub_doc.id,
                                 principal=f"user:{andi.id}")
            await share_document(session, authz, actor=owner, document_id=conf_doc.id,
                                 principal=f"user:{andi.id}")

            # Andi sees both with no filter
            all_results = await search_documents(session, user=andi, query="Announcement OR Report")
            # Use title-based search for each individually
            pub_results = await search_documents(session, user=andi, query="Public Announcement")
            conf_results = await search_documents(session, user=andi, query="Confidential Report")
            assert len(pub_results) == 1
            assert len(conf_results) == 1

            # Filter by sensitivity=public narrows to only the public doc
            pub_only = await search_documents(session, user=andi, query="Announcement",
                                              sensitivity="public")
            assert len(pub_only) == 1
            assert pub_only[0]["sensitivity"] == "public"

            # Filter by sensitivity=confidential should not show the public doc
            conf_only = await search_documents(session, user=andi, query="Announcement",
                                               sensitivity="confidential")
            assert conf_only == []

            # Trash the public doc — it should vanish from search
            await trash_document(session, actor=owner, document_id=pub_doc.id)
            after_trash = await search_documents(session, user=andi, query="Public Announcement")
            assert after_trash == []

            # View filter: my_documents only shows owner's own
            owner_view = await search_documents(session, user=andi, query="Confidential Report",
                                                view="my_documents")
            assert owner_view == []  # Andi doesn't own it

            # Sensitivity filter cannot widen: even with sensitivity filter, unshared docs stay hidden
            unshared_doc = await create_seeded_document(
                session, owner=owner, title="Hidden Internal",
                text="Should not appear for budi.",
            )
            from e2eai.db import User as UserModel
            budi = await session.scalar(select(UserModel).where(func.lower(UserModel.email) == "budi@demo.e2eai"))
            widened = await search_documents(session, user=budi, query="Hidden Internal",
                                             sensitivity="internal")
            assert widened == []

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 6. Revoke removes result immediately
# ---------------------------------------------------------------------------
def test_revoke_removes_search_result_immediately():
    """FR-S10: after revoking a share, the document disappears from the next search."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="Revocable Doc",
                text="Content that will be revoked.",
            )
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id,
                                 principal=f"user:{andi.id}", level="viewer")

            # Andi can find it before revoke
            before = await search_documents(session, user=andi, query="Revocable")
            assert len(before) == 1

            # Revoke
            await revoke_document(session, authz, actor=owner, document_id=doc.id,
                                  principal=f"user:{andi.id}", level="viewer")

            # Andi cannot find it after revoke
            after = await search_documents(session, user=andi, query="Revocable")
            assert after == []
            # No title leak
            assert "Revocable" not in str(after)

    _migrate()
    asyncio.run(run())
