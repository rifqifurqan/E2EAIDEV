"""FR-X2 Live MCP tool-call planner: question-time tool selection and no-vectorize guard.

At question time the system plans MCP tool calls from existing descriptors.
Live tool results are NEVER indexed or vectorized. Tests verify:
- Tool-call planning from an MCP descriptor + question
- Safe output: no auth secrets, server URLs, raw payloads, or credentials
- Vectorize/embed guard rejects live tool results
- read_only enforcement: mutating tools require confirmation flag
- Audit records planned calls with safe metadata only
- API route wiring
"""

import pytest

from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor, build_mcp_server_descriptor
from e2eai.mcp_tool_call import (
    LiveToolResult,
    MCPToolCallRecord,
    build_mcp_tool_plan_response,
    plan_mcp_tool_calls,
    reject_vectorize_live_result,
)

# ---------------------------------------------------------------------------
# Fixtures: reuse the HR API spec from mcp_gen tests
# ---------------------------------------------------------------------------

HR_DESCRIPTOR = MCPServerDescriptor(
    system_id="hr-system",
    mcp_server_name="hr-system.mcp",
    tools=[
        MCPToolDescriptor(
            name="list_employees",
            description="List all employees",
            operation_id="list_employees",
            method="GET",
            path="/employees",
            read_only=True,
            parameters=[{"name": "department", "in": "query", "required": False, "schema": {"type": "string"}}],
        ),
        MCPToolDescriptor(
            name="get_employee",
            description="Get employee by ID",
            operation_id="get_employee",
            method="GET",
            path="/employees/{id}",
            read_only=True,
            parameters=[{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        ),
        MCPToolDescriptor(
            name="create_employee",
            description="Create a new employee",
            operation_id="create_employee",
            method="POST",
            path="/employees",
            read_only=False,
            parameters=[],
        ),
    ],
    spec_summary={"spec_title": "HR API", "spec_version": "1.0.0", "total_operation_count": 3, "allowed_count": 3},
)


# ---------------------------------------------------------------------------
# Tool-call planning
# ---------------------------------------------------------------------------


def test_plan_selects_relevant_tools_from_descriptor():
    """A question about employees should match employee-related tools."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="How many employees are in the Sales department?",
    )
    assert len(records) >= 1
    op_ids = {r.operation_id for r in records}
    assert "list_employees" in op_ids
    for r in records:
        assert isinstance(r, MCPToolCallRecord)


def test_plan_returns_empty_for_unrelated_question():
    """A question about weather should not match any HR tools."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="What is the weather forecast for tomorrow?",
    )
    assert records == []


def test_plan_returns_empty_for_empty_descriptors():
    records = plan_mcp_tool_calls(descriptors=[], question="How many employees?")
    assert records == []


def test_plan_record_carries_safe_metadata():
    """Records must carry operation_id, method, path, read_only, system_id but no secrets."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="List employees in the sales department",
    )
    assert len(records) >= 1
    r = records[0]
    assert r.system_id == "hr-system"
    assert r.operation_id == "list_employees"
    assert r.method == "GET"
    assert r.path == "/employees"
    assert r.read_only is True
    # Safe: no auth, no URL, no payload
    serialized = str(r)
    assert "bearer" not in serialized.lower()
    assert "api-key" not in serialized.lower().replace("_", "-")
    assert "secret" not in serialized.lower()


def test_plan_flags_mutating_tools_needing_confirmation():
    """Mutating (non-read_only) tools in the plan must be flagged as needs_confirmation=True."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="Create a new employee named Alice in Engineering",
    )
    mutating = [r for r in records if not r.read_only]
    assert len(mutating) >= 1
    for r in mutating:
        assert r.needs_confirmation is True, (
            f"Mutating tool {r.operation_id} must have needs_confirmation=True"
        )


def test_plan_response_does_not_echo_raw_question_or_payload():
    """Question text may contain secrets; route/helper responses expose only safe call metadata."""
    response = build_mcp_tool_plan_response(
        descriptors=[HR_DESCRIPTOR],
        question="List employees with bearer token prod-secret-api-key",
    )
    serialized = str(response).lower()
    assert "question" not in response
    assert "prod-secret-api-key" not in serialized
    assert "bearer token" not in serialized
    assert response["total"] >= 1
    assert response["planned_calls"][0]["operation_id"] == "list_employees"


def test_plan_read_only_tools_do_not_need_confirmation():
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="List all employees",
    )
    read_only = [r for r in records if r.read_only]
    assert len(read_only) >= 1
    for r in read_only:
        assert r.needs_confirmation is False


# ---------------------------------------------------------------------------
# No-vectorize guard (FR-X2 core invariant)
# ---------------------------------------------------------------------------


def test_reject_vectorize_live_result_raises():
    """Attempting to vectorize/embed/index a live tool result must raise."""
    result = LiveToolResult(
        system_id="hr-system",
        operation_id="list_employees",
        source="live_mcp",
    )
    with pytest.raises(ValueError, match="[Ll]ive.*tool.*result.*must not.*vector|index|embed"):
        reject_vectorize_live_result(result)


def test_reject_vectorize_marks_source_as_live():
    """LiveToolResult always declares its source as live_mcp."""
    result = LiveToolResult(
        system_id="hr-system",
        operation_id="get_employee",
        source="live_mcp",
    )
    assert result.source == "live_mcp"
    assert result.vectorizable is False


# ---------------------------------------------------------------------------
# Multiple descriptors
# ---------------------------------------------------------------------------


ERP_DESCRIPTOR = MCPServerDescriptor(
    system_id="erp-system",
    mcp_server_name="erp-system.mcp",
    tools=[
        MCPToolDescriptor(
            name="get_purchase_order",
            description="Get purchase order details",
            operation_id="get_purchase_order",
            method="GET",
            path="/purchase-orders/{id}",
            read_only=True,
            parameters=[{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        ),
    ],
    spec_summary={"spec_title": "ERP API", "spec_version": "2.0.0", "total_operation_count": 1, "allowed_count": 1},
)


def test_plan_matches_across_multiple_descriptors():
    """When multiple descriptors are provided, tools from the right system are selected."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR, ERP_DESCRIPTOR],
        question="Show me the purchase order details",
    )
    op_ids = {r.operation_id for r in records}
    assert "get_purchase_order" in op_ids
    # Should NOT include unrelated HR tools
    assert "list_employees" not in op_ids


# ---------------------------------------------------------------------------
# API route wiring
# ---------------------------------------------------------------------------


def test_mcp_tool_call_plan_route_is_wired():
    """POST /api/v1/chat/mcp-tool-plan is registered in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/chat/mcp-tool-plan" in openapi["paths"], (
        f"Route not found. Registered paths: {sorted(openapi['paths'].keys())}"
    )


# ---------------------------------------------------------------------------
# DB-backed pipeline integration tests (FR-X2 chat pipeline wiring)
# ---------------------------------------------------------------------------


def test_send_message_with_descriptors_persists_tool_call_records():
    """FR-X2: send_message with MCP descriptors plans, executes (offline), persists, and audits tool calls."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            AuditEntry, Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, McpToolCall, Message, MessageCitation, User, sessions,
        )
        from e2eai.documents import create_seeded_document, share_document
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

            conv = await create_conversation(session, user=andi, title="HR chat")
            executor = OfflineExecutor(results={"list_employees": {"record_count": 5, "status": "ok"}})

            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees are there?",
                embedder=_Embedder(),
                descriptors=[HR_DESCRIPTOR],
                executor=executor,
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            assert asst_msg is not None

            tc_rows = (await session.execute(
                select(McpToolCall).where(McpToolCall.message_id == asst_msg.id)
            )).scalars().all()
            assert len(tc_rows) >= 1
            tc = next((t for t in tc_rows if t.operation_id == "list_employees"), None)
            assert tc is not None, "list_employees tool call not persisted"
            assert tc.system_id == "hr-system"
            assert tc.read_only is True
            assert tc.status == "executed"

            audit_rows = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.in_([
                    "mcp.tool_call.executed", "mcp.tool_call.skipped"
                ]))
            )).scalars().all()
            assert len(audit_rows) >= 1

            assert "tool_calls" in result

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_tool_call_records_store_safe_metadata_only():
    """FR-X2: McpToolCall rows never contain secrets, server URLs, raw question text, or payloads."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, McpToolCall, Message, MessageCitation, User, sessions,
        )
        from e2eai.documents import create_seeded_document, share_document
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
                session, owner=owner, title="Employees doc",
                text="There are 10 employees in HR.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Leak check")
            await send_message(
                session, user=andi, conversation_id=conv.id,
                question="List employees with bearer token secret-key-abc",
                embedder=_Embedder(),
                descriptors=[HR_DESCRIPTOR],
                executor=OfflineExecutor(),
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            tc_rows = (await session.execute(
                select(McpToolCall).where(McpToolCall.message_id == asst_msg.id)
            )).scalars().all()

            for tc in tc_rows:
                row_str = str({
                    "system_id": tc.system_id, "operation_id": tc.operation_id,
                    "method": tc.method, "path": tc.path, "safe_result": tc.safe_result,
                }).lower()
                assert "secret-key-abc" not in row_str
                assert "bearer token" not in row_str
                assert "list employees with" not in row_str  # raw question not stored

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_sanitize_mcp_safe_result_removes_secret_like_fields_recursively():
    """FR-X2: executor result summaries must be scrubbed before persistence/response."""
    from e2eai.mcp_tool_call import sanitize_mcp_safe_result

    raw = {
        "status": "ok",
        "record_count": 2,
        "authorization": "Bearer secret-token-123",
        "server_url": "https://internal.example.local/hr",
        "payload": {"employee": "Andi", "token": "abc123"},
        "nested": {"api_key": "key-123", "safe_count": 4},
        "items": [{"result_count": 4, "access_token": "tok"}],
    }

    safe = sanitize_mcp_safe_result(raw)
    safe_str = str(safe).lower()

    assert safe["status"] == "ok"
    assert safe["record_count"] == 2
    assert safe["nested"]["safe_count"] == 4
    assert safe["items"][0]["result_count"] == 4
    assert "secret-token-123" not in safe_str
    assert "internal.example.local" not in safe_str
    assert "abc123" not in safe_str
    assert "key-123" not in safe_str
    assert "authorization" not in safe_str
    assert "server_url" not in safe_str
    assert "payload" not in safe_str
    assert "api_key" not in safe_str
    assert "access_token" not in safe_str



def test_send_message_without_descriptors_backward_compatible():
    """FR-X2: send_message without descriptors param works unchanged (no tool_calls or empty list)."""
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
                session, owner=owner, title="Employees doc",
                text="There are 10 employees.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Backward compat")
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees?",
                embedder=_Embedder(),
                # No descriptors or executor — existing usage
            )

            assert result.get("tool_calls", []) == []

            msgs = (await session.execute(
                select(Message).where(Message.conversation_id == conv.id)
            )).scalars().all()
            assert len(msgs) == 2

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())
