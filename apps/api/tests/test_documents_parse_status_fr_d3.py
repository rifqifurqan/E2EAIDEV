"""FR-D3 / FR-F20: the document list must report the real ingest status of the current version.
Rich files are parsed by a background worker, so the library has to show 'pending' -> 'ready' / 'failed'
(it used to answer 'available' for everything, which the UI could not poll)."""

import asyncio

from sqlalchemy import func, select

from e2eai.db import DocumentVersion, User, sessions
from e2eai.documents import create_uploaded_document, list_documents_view, search_documents
from e2eai.seed import seed_demo


class _Storage:
    async def put_bytes(self, data: bytes):
        return "sha256/test", "test-digest"


async def _andi(session) -> User:
    await seed_demo(session, password="TestPassword_123456789")
    return await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))


async def _upload(session, owner, title, mime="application/pdf"):
    doc = await create_uploaded_document(session, owner=owner, title=title, data=b"%PDF-1.7 x", mime=mime, storage=_Storage())
    await session.commit()
    return doc


def _row(rows, title):
    return next(r for r in rows if r["title"] == title)


def test_the_list_shows_pending_then_ready_with_the_scan_status_and_confidence():
    async def run():
        async with sessions()() as session:
            andi = await _andi(session)
            doc = await _upload(session, andi, "contract.pdf")

            row = _row(await list_documents_view(session, user=andi, view="my_documents"), "contract.pdf")
            assert (row["parse_status"], row["scan_status"]) == ("pending", "pending")

            version = await session.get(DocumentVersion, doc.current_version_id)
            version.parse_status, version.scan_status, version.parse_confidence = "ready", "clean", 0.42
            await session.commit()

            row = _row(await list_documents_view(session, user=andi, view="my_documents"), "contract.pdf")
            assert (row["parse_status"], row["scan_status"], row["parse_confidence"]) == ("ready", "clean", 0.42)

    asyncio.run(run())


def test_a_failed_parse_is_visible_in_the_list():
    async def run():
        async with sessions()() as session:
            andi = await _andi(session)
            doc = await _upload(session, andi, "broken.pdf")
            version = await session.get(DocumentVersion, doc.current_version_id)
            version.parse_status = "failed"
            await session.commit()
            assert _row(await list_documents_view(session, user=andi, view="my_documents"), "broken.pdf")["parse_status"] == "failed"

    asyncio.run(run())


def test_a_trashed_document_keeps_reporting_its_status():
    async def run():
        from e2eai.documents import trash_document

        async with sessions()() as session:
            andi = await _andi(session)
            doc = await _upload(session, andi, "old.pdf")
            await trash_document(session, actor=andi, document_id=doc.id)
            await session.commit()
            assert _row(await list_documents_view(session, user=andi, view="trash"), "old.pdf")["parse_status"] == "pending"

    asyncio.run(run())


def test_search_results_carry_the_status_too():
    async def run():
        async with sessions()() as session:
            andi = await _andi(session)
            await _upload(session, andi, "searchable-agreement.pdf")
            rows = await search_documents(session, user=andi, query="searchable-agreement")
            assert _row(rows, "searchable-agreement.pdf")["parse_status"] == "pending"

    asyncio.run(run())


def test_the_paginated_search_used_by_the_api_carries_the_status_too():
    async def run():
        from e2eai.documents import search_documents_page

        async with sessions()() as session:
            andi = await _andi(session)
            await _upload(session, andi, "paged-agreement.pdf")
            rows, _ = await search_documents_page(session, user=andi, query="paged-agreement")
            assert _row(rows, "paged-agreement.pdf")["parse_status"] == "pending"

    asyncio.run(run())
