"""FR-X5 Read-only by default; write actions require explicit user confirmation and audit.

The existing FR-X2 planner already flags mutating tools (needs_confirmation=True)
and skips them during execution. FR-X5 adds:
- Explicit user confirmation of a pending write action
- Confirmed write actions are executed and audited
- Denied write actions are recorded as denied
- Safe audit records: user who confirmed, operation, system — never raw tokens
- Route wiring for confirmation endpoint
"""

import pytest


# ---------------------------------------------------------------------------
# Unit tests: write confirmation service
# ---------------------------------------------------------------------------


def test_pending_write_tool_call_can_be_confirmed():
    """A pending/skipped mutating tool call can be confirmed by the user."""
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
        from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor
        from e2eai.mcp_tool_call import OfflineExecutor
        from e2eai.retrieval import index_document_chunks
        from e2eai.seed import seed_demo
        from e2eai.write_confirmation import confirm_tool_call

        class _Authz:
            async def write(self, writes=(), deletes=()):
                return None

        class _Embedder:
            model = "fake-v1"
            _axes = ("employees", "create")
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
                title="HR Policy", text="Employee benefits and create procedures.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            hr_desc = MCPServerDescriptor(
                system_id="hr-system",
                mcp_server_name="hr-system.mcp",
                tools=[
                    MCPToolDescriptor(
                        name="create_employee", description="Create a new employee",
                        operation_id="create_employee", method="POST",
                        path="/employees", read_only=False, parameters=[],
                    ),
                ],
                spec_summary={},
            )

            conv = await create_conversation(session, user=andi, title="Write test")
            executor = OfflineExecutor(results={"create_employee": {"created_id": "emp-42"}})
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="Create a new employee named Alice",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            # The mutating tool should be skipped initially
            skipped = [tc for tc in result["tool_calls"] if tc["status"] == "skipped_confirmation"]
            assert len(skipped) >= 1

            # Find the pending McpToolCall row
            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            pending_tc = await session.scalar(
                select(McpToolCall).where(
                    McpToolCall.message_id == asst_msg.id,
                    McpToolCall.status == "skipped_confirmation",
                )
            )
            assert pending_tc is not None

            # User confirms the write action
            confirm_result = await confirm_tool_call(
                session,
                tool_call_id=pending_tc.id,
                user=andi,
                decision="confirm",
                executor=executor,
            )
            assert confirm_result["status"] == "confirmed_executed"

            await session.refresh(pending_tc)
            assert pending_tc.status == "confirmed_executed"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_pending_write_tool_call_can_be_denied():
    """A pending mutating tool call can be denied by the user."""
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
        from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor
        from e2eai.mcp_tool_call import OfflineExecutor
        from e2eai.retrieval import index_document_chunks
        from e2eai.seed import seed_demo
        from e2eai.write_confirmation import confirm_tool_call

        class _Authz:
            async def write(self, writes=(), deletes=()):
                return None

        class _Embedder:
            model = "fake-v1"
            _axes = ("employees", "create")
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
                title="HR Policy", text="Employee create procedures.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            hr_desc = MCPServerDescriptor(
                system_id="hr-system",
                mcp_server_name="hr-system.mcp",
                tools=[
                    MCPToolDescriptor(
                        name="create_employee", description="Create a new employee",
                        operation_id="create_employee", method="POST",
                        path="/employees", read_only=False, parameters=[],
                    ),
                ],
                spec_summary={},
            )

            conv = await create_conversation(session, user=andi, title="Deny test")
            executor = OfflineExecutor()
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="Create a new employee",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            pending_tc = await session.scalar(
                select(McpToolCall).where(
                    McpToolCall.message_id == asst_msg.id,
                    McpToolCall.status == "skipped_confirmation",
                )
            )

            deny_result = await confirm_tool_call(
                session,
                tool_call_id=pending_tc.id,
                user=andi,
                decision="deny",
                executor=executor,
            )
            assert deny_result["status"] == "denied"

            await session.refresh(pending_tc)
            assert pending_tc.status == "denied"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_confirmation_audit_record_is_safe():
    """Audit for confirmed writes must include user_id, system_id, operation — never tokens."""
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
        from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor
        from e2eai.mcp_tool_call import OfflineExecutor
        from e2eai.retrieval import index_document_chunks
        from e2eai.seed import seed_demo
        from e2eai.write_confirmation import confirm_tool_call

        class _Authz:
            async def write(self, writes=(), deletes=()):
                return None

        class _Embedder:
            model = "fake-v1"
            _axes = ("employees", "create")
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
                title="HR Policy", text="Employee create procedures.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

            hr_desc = MCPServerDescriptor(
                system_id="hr-system",
                mcp_server_name="hr-system.mcp",
                tools=[MCPToolDescriptor(
                    name="create_employee", description="Create a new employee",
                    operation_id="create_employee", method="POST",
                    path="/employees", read_only=False, parameters=[],
                )],
                spec_summary={},
            )

            conv = await create_conversation(session, user=andi, title="Audit test")
            executor = OfflineExecutor(results={"create_employee": {"created_id": "emp-99"}})
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="Create employee Alice",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            pending_tc = await session.scalar(
                select(McpToolCall).where(
                    McpToolCall.message_id == asst_msg.id,
                    McpToolCall.status == "skipped_confirmation",
                )
            )

            await confirm_tool_call(
                session, tool_call_id=pending_tc.id, user=andi,
                decision="confirm", executor=executor,
            )

            audit_rows = (await session.execute(
                select(AuditEntry).where(
                    AuditEntry.action == "mcp.tool_call.confirmed"
                )
            )).scalars().all()
            assert len(audit_rows) >= 1
            latest = audit_rows[-1]
            assert latest.details.get("operation_id") == "create_employee"
            assert latest.details.get("system_id") == "hr-system"
            assert latest.details.get("confirmed_by") == str(andi.id)
            audit_str = str(latest.details).lower()
            assert "bearer" not in audit_str
            assert "secret" not in audit_str
            assert "token_value" not in audit_str

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_read_only_tools_execute_without_confirmation():
    """Read-only tools must execute immediately without any confirmation step."""
    from e2eai.mcp_tool_call import MCPToolCallRecord, plan_mcp_tool_calls
    from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor

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
    records = plan_mcp_tool_calls(descriptors=[hr_desc], question="List all employees")
    assert len(records) >= 1
    for r in records:
        assert r.read_only is True
        assert r.needs_confirmation is False


def test_write_confirmation_route_is_wired():
    """POST /api/v1/chat/tool-calls/{tool_call_id}/confirm is registered."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/chat/tool-calls/{tool_call_id}/confirm" in openapi["paths"], (
        f"Route not found. Registered paths: {sorted(openapi['paths'].keys())}"
    )
