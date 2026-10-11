"""FR-X6 Answers combine documents and live data with citations for both:
document page + system record ID.

Tests verify:
- Combined citation format merges document citations and live MCP tool-call results
- Document citations carry source=document, page, section
- Live data citations carry source=live_system, system_id, operation_id, record_id
- Safe output: no raw tokens, server URLs, or credentials in any citation
- build_combined_citations is deterministic and offline
- Route: send_message result includes combined_citations when tool calls + doc citations present
"""

import pytest


# ---------------------------------------------------------------------------
# Unit tests: combined citation builder
# ---------------------------------------------------------------------------


def test_build_combined_citations_from_doc_and_tools():
    """Combined citations merge document and live system citations."""
    from e2eai.combined_citations import build_combined_citations

    doc_citations = [
        {"document": "HR Policy", "page": 3, "section": "Benefits"},
    ]
    tool_call_results = [
        {"operation_id": "list_employees", "status": "executed",
         "system_id": "hr-system", "safe_result": {"record_count": 5, "record_id": "dept:sales"}},
    ]

    combined = build_combined_citations(
        doc_citations=doc_citations,
        tool_call_results=tool_call_results,
    )

    assert len(combined) == 2

    doc_cite = next(c for c in combined if c["source"] == "document")
    assert doc_cite["document"] == "HR Policy"
    assert doc_cite["page"] == 3
    assert doc_cite["section"] == "Benefits"

    live_cite = next(c for c in combined if c["source"] == "live_system")
    assert live_cite["system_id"] == "hr-system"
    assert live_cite["operation_id"] == "list_employees"
    assert live_cite["record_id"] == "dept:sales"


def test_combined_citations_doc_only():
    """When no tool calls, combined citations contain only document citations."""
    from e2eai.combined_citations import build_combined_citations

    doc_citations = [
        {"document": "Policy", "page": 1, "section": "Intro"},
    ]

    combined = build_combined_citations(doc_citations=doc_citations, tool_call_results=[])
    assert len(combined) == 1
    assert combined[0]["source"] == "document"


def test_combined_citations_live_only():
    """When no doc citations, combined citations contain only live system citations."""
    from e2eai.combined_citations import build_combined_citations

    tool_results = [
        {"operation_id": "get_order", "status": "executed",
         "system_id": "erp", "safe_result": {"order_id": "PO-123"}},
    ]

    combined = build_combined_citations(doc_citations=[], tool_call_results=tool_results)
    assert len(combined) == 1
    assert combined[0]["source"] == "live_system"
    assert combined[0]["system_id"] == "erp"
    assert combined[0]["operation_id"] == "get_order"


def test_combined_citations_exclude_skipped_and_rejected():
    """Skipped/rejected tool calls should not appear as live citations."""
    from e2eai.combined_citations import build_combined_citations

    tool_results = [
        {"operation_id": "list_employees", "status": "executed", "system_id": "hr"},
        {"operation_id": "create_employee", "status": "skipped_confirmation", "system_id": "hr"},
        {"operation_id": "delete_employee", "status": "rejected_service_account", "system_id": "hr"},
    ]

    combined = build_combined_citations(doc_citations=[], tool_call_results=tool_results)
    assert len(combined) == 1
    assert combined[0]["operation_id"] == "list_employees"


def test_combined_citations_never_contain_secrets():
    """Combined citations must never contain raw tokens, server URLs, or credentials."""
    from e2eai.combined_citations import build_combined_citations

    doc_citations = [{"document": "Doc", "page": 1, "section": "S"}]
    tool_results = [
        {"operation_id": "get_data", "status": "executed", "system_id": "sys",
         "safe_result": {"count": 3, "authorization": "Bearer xyz", "server_url": "https://x.y/api"}},
    ]

    combined = build_combined_citations(
        doc_citations=doc_citations,
        tool_call_results=tool_results,
    )
    combined_str = str(combined).lower()
    assert "bearer" not in combined_str
    assert "xyz" not in combined_str
    assert "x.y/api" not in combined_str
    assert "server_url" not in combined_str
    assert "authorization" not in combined_str


def test_combined_citations_empty_inputs():
    """No citations and no tool calls yields empty list."""
    from e2eai.combined_citations import build_combined_citations

    assert build_combined_citations(doc_citations=[], tool_call_results=[]) == []


def test_send_message_returns_combined_citations():
    """FR-X6: send_message with descriptors includes combined_citations in result."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, Message, MessageCitation, User, sessions,
        )
        from e2eai.documents import create_seeded_document, share_document
        from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor
        from e2eai.mcp_tool_call import OfflineExecutor
        from e2eai.retrieval import index_document_chunks
        from e2eai.seed import seed_demo

        class _Authz:
            async def write(self, writes=(), deletes=()):
                return None

        class _Embedder:
            model = "fake-v1"
            _axes = ("employees", "revenue")
            async def embed(self, texts):
                return [[float(t.lower().count(a)) for a in self._axes] for t in texts]

        async with sessions()() as session:
            for m in (MessageCitation, Message, Conversation,
                      ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
                await session.execute(delete(m))
            await session.commit()

            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))

            doc = await create_seeded_document(
                session, owner=owner,
                title="HR Policy", text="The HR policy covers employee benefits.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            hr_desc = MCPServerDescriptor(
                system_id="hr-system",
                mcp_server_name="hr-system.mcp",
                tools=[MCPToolDescriptor(
                    name="list_employees", description="List all employees",
                    operation_id="list_employees", method="GET",
                    path="/employees", read_only=True, parameters=[],
                )],
                spec_summary={},
            )

            conv = await create_conversation(session, user=andi, title="Combined citation")
            executor = OfflineExecutor(results={"list_employees": {"record_count": 5, "record_id": "hr:employees"}})

            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees are there?",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            assert "combined_citations" in result
            combined = result["combined_citations"]
            assert len(combined) >= 2  # at least 1 doc + 1 live

            sources = {c["source"] for c in combined}
            assert "document" in sources
            assert "live_system" in sources
            live_cite = next(c for c in combined if c["source"] == "live_system")
            assert live_cite["record_id"] == "hr:employees"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())
