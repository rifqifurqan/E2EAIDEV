"""FR-X1 knowledge connectors with permission mirroring.

Deterministic/offline: a fake connector yields source documents with source-system ACLs; the sync maps
them onto local principals (fail closed: unmapped groups and public links are dropped), mirrors the ACL
exactly (tighten first), and trashes documents removed from the source. No credentials are stored.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, Chunk, DocPrincipal, Document, DocumentVersion, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


class FakeAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=None, deletes=None):
        self.calls.append(("write" if writes else "delete", list(writes or deletes or [])))


async def _reset(session):
    from e2eai.db import ConnectorDocument

    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("connector.%")))
    old = (await session.scalars(select(ConnectorDocument.document_id))).all()
    await session.execute(delete(ConnectorDocument))
    if old:
        await session.execute(delete(Document).where(Document.id.in_(old)))
    await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return admin, andi, budi


def _doc(ext_id, title, text, acl):
    from e2eai.connectors import SourceDocument

    return SourceDocument(external_id=ext_id, title=title, text=text, acl=acl)


async def _visible_titles(session, principals):
    from e2eai.documents import visible_chunks

    # the shared test DB may hold other tests' documents: only look at this test's own titles
    mine = {"HR handbook", "Payroll", "Policy"}
    return {t for t, _, _ in await visible_chunks(session, principals)} & mine


def test_sync_mirrors_acl_fail_closed_and_drops_actor_ownership():
    async def run():
        from e2eai.connectors import FakeConnector, sync_connector

        async with sessions()() as session:
            admin, andi, budi = await _reset(session)
            conn = FakeConnector("gdrive:main", [
                _doc("f1", "HR handbook", "Leave is 12 days.", [
                    {"type": "user", "email": "ANDI@demo.e2eai"},
                    {"type": "group", "id": "unmapped-group"},
                    {"type": "anyone"},
                ]),
            ])
            report = await sync_connector(session, FakeAuthz(), actor=admin, connector=conn)
            assert report["created"] == 1 and report["updated"] == 0 and report["trashed"] == 0
            assert report["principals_mapped"] == 1
            assert report["principals_dropped"] == {"unmapped_group": 1, "public": 1, "unknown_user": 0}

            assert await _visible_titles(session, [f"user:{andi.id}"]) == {"HR handbook"}
            assert await _visible_titles(session, [f"user:{budi.id}"]) == set()
            assert await _visible_titles(session, [f"user:{admin.id}"]) == set()  # syncing admin gets no implicit access

            audits = (await session.scalars(select(AuditEntry).where(AuditEntry.action == "connector.sync"))).all()
            assert len(audits) == 1 and set(audits[0].details) <= {"source", "created", "updated", "trashed", "principals_mapped", "principals_dropped", "unchanged"}
            assert "Leave is 12" not in str(audits[0].details) and "ANDI@" not in str(audits[0].details)

    _migrate()
    asyncio.run(run())


def test_group_mapping_resync_idempotent_and_acl_tightening():
    async def run():
        from e2eai.connectors import FakeConnector, sync_connector

        async with sessions()() as session:
            admin, andi, budi = await _reset(session)
            gm = {"hr-team": f"user:{budi.id}"}  # source group -> local principal
            conn = FakeConnector("gdrive:main", [
                _doc("f1", "Payroll", "Salary bands", [{"type": "user", "email": "andi@demo.e2eai"}, {"type": "group", "id": "hr-team"}]),
            ])
            await sync_connector(session, FakeAuthz(), actor=admin, connector=conn, group_map=gm)
            assert await _visible_titles(session, [f"user:{budi.id}"]) == {"Payroll"}

            again = await sync_connector(session, FakeAuthz(), actor=admin, connector=conn, group_map=gm)
            assert again["created"] == 0 and again["updated"] == 0 and again["unchanged"] == 1

            # source removes the hr-team share: access must disappear on the next sync
            authz = FakeAuthz()
            conn.documents = [_doc("f1", "Payroll", "Salary bands", [{"type": "user", "email": "andi@demo.e2eai"}])]
            tightened = await sync_connector(session, authz, actor=admin, connector=conn, group_map=gm)
            assert tightened["updated"] == 1
            assert await _visible_titles(session, [f"user:{budi.id}"]) == set()
            assert await _visible_titles(session, [f"user:{andi.id}"]) == {"Payroll"}
            assert authz.calls and authz.calls[0][0] == "delete"  # revocation is sent to OpenFGA

    _migrate()
    asyncio.run(run())


def test_content_change_adds_version_and_removed_source_doc_is_trashed():
    async def run():
        from e2eai.connectors import FakeConnector, sync_connector

        async with sessions()() as session:
            admin, andi, budi = await _reset(session)
            conn = FakeConnector("gdrive:main", [_doc("f1", "Policy", "Old text", [{"type": "user", "email": "andi@demo.e2eai"}])])
            await sync_connector(session, FakeAuthz(), actor=admin, connector=conn)
            conn.documents = [_doc("f1", "Policy", "New text", [{"type": "user", "email": "andi@demo.e2eai"}])]
            res = await sync_connector(session, FakeAuthz(), actor=admin, connector=conn)
            assert res["updated"] == 1
            doc = await session.scalar(select(Document).where(Document.title == "Policy"))
            versions = (await session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))).all()
            assert len(versions) == 2
            current = await session.scalar(select(Chunk.text).where(Chunk.version_id == doc.current_version_id))
            assert current == "New text"

            conn.documents = []  # deleted at the source
            gone = await sync_connector(session, FakeAuthz(), actor=admin, connector=conn)
            assert gone["trashed"] == 1
            await session.refresh(doc)
            assert doc.status == "trashed"
            assert await _visible_titles(session, [f"user:{andi.id}"]) == set()

    _migrate()
    asyncio.run(run())


def test_non_admin_cannot_sync_and_credentials_are_never_stored():
    async def run():
        from e2eai.connectors import FakeConnector, sync_connector

        async with sessions()() as session:
            admin, andi, budi = await _reset(session)
            with pytest.raises(AppError) as exc:
                await sync_connector(session, FakeAuthz(), actor=andi, connector=FakeConnector("gdrive:main", []))
            assert exc.value.status == 403

    _migrate()
    asyncio.run(run())

    from e2eai.db import ConnectorDocument

    cols = {c.name for c in ConnectorDocument.__table__.columns}
    assert not {"token", "credentials", "password", "secret", "api_key"} & cols


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/connectors/sync"]
