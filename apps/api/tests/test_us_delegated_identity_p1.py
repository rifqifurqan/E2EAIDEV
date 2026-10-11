"""FR-X3 Delegated identity / token exchange for MCP tool calls.

AI calls system APIs with the asking user's identity (OAuth token exchange or
per-user delegated token). A super-admin service account is never used for user data.

Tests verify:
- DelegatedIdentityContext carries user_id, system_id, auth_mode without raw tokens
- SERVICE_ACCOUNT auth mode is rejected / fails closed for user-data calls
- Executor with identity context persists auth_mode + acting_user_id in McpToolCall
- Audit records contain user_id + system_id + auth_mode, never token values
- Safe output: no raw token values in serialized context, audit, DB rows, or API responses
- Wire into send_message with identity context proves calls execute as the asking user
"""

import pytest

# ---------------------------------------------------------------------------
# Unit tests: DelegatedIdentityContext and validation
# ---------------------------------------------------------------------------


def test_delegated_identity_context_carries_safe_metadata():
    """Context must carry user_id, system_id, auth_mode — no raw tokens."""
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext

    ctx = DelegatedIdentityContext(
        user_id="user-123",
        system_id="hr-system",
        auth_mode=AuthMode.TOKEN_EXCHANGE,
    )
    assert ctx.user_id == "user-123"
    assert ctx.system_id == "hr-system"
    assert ctx.auth_mode == AuthMode.TOKEN_EXCHANGE
    serialized = str(ctx)
    assert "bearer" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert "password" not in serialized.lower()


def test_delegated_identity_context_with_delegated_mode():
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext

    ctx = DelegatedIdentityContext(
        user_id="user-456",
        system_id="erp-system",
        auth_mode=AuthMode.DELEGATED,
    )
    assert ctx.auth_mode == AuthMode.DELEGATED
    assert ctx.user_id == "user-456"


def test_service_account_rejected_for_user_data():
    """FR-X3 core: SERVICE_ACCOUNT must be rejected/fail closed for user-data calls."""
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext, validate_identity_for_user_data

    ctx = DelegatedIdentityContext(
        user_id="svc-admin",
        system_id="hr-system",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
    )
    with pytest.raises(ValueError, match="[Ss]ervice.account.*not.*allowed|[Dd]elegated.*identity.*required"):
        validate_identity_for_user_data(ctx)


def test_token_exchange_accepted_for_user_data():
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext, validate_identity_for_user_data

    ctx = DelegatedIdentityContext(
        user_id="user-123",
        system_id="hr-system",
        auth_mode=AuthMode.TOKEN_EXCHANGE,
    )
    # Should not raise
    validate_identity_for_user_data(ctx)


def test_delegated_mode_accepted_for_user_data():
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext, validate_identity_for_user_data

    ctx = DelegatedIdentityContext(
        user_id="user-123",
        system_id="hr-system",
        auth_mode=AuthMode.DELEGATED,
    )
    validate_identity_for_user_data(ctx)


def test_missing_user_id_rejected():
    """Identity context without a user_id must fail closed."""
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext, validate_identity_for_user_data

    ctx = DelegatedIdentityContext(
        user_id="",
        system_id="hr-system",
        auth_mode=AuthMode.TOKEN_EXCHANGE,
    )
    with pytest.raises(ValueError, match="[Uu]ser.*id.*required|[Ii]dentity.*missing"):
        validate_identity_for_user_data(ctx)


def test_safe_audit_metadata_from_identity():
    """Audit metadata must include user_id, system_id, auth_mode — never token values."""
    from e2eai.delegated_identity import AuthMode, DelegatedIdentityContext, safe_audit_metadata

    ctx = DelegatedIdentityContext(
        user_id="user-789",
        system_id="erp-system",
        auth_mode=AuthMode.TOKEN_EXCHANGE,
    )
    meta = safe_audit_metadata(ctx)
    assert meta["acting_user_id"] == "user-789"
    assert meta["system_id"] == "erp-system"
    assert meta["auth_mode"] == "token_exchange"
    meta_str = str(meta).lower()
    assert "bearer" not in meta_str
    assert "secret" not in meta_str
    assert "token_value" not in meta_str
    assert "password" not in meta_str
    assert "api_key" not in meta_str


# ---------------------------------------------------------------------------
# Executor integration: DelegatedExecutor wraps the Executor protocol
# ---------------------------------------------------------------------------


def test_delegated_executor_requires_valid_identity():
    """DelegatedExecutor must reject execution with SERVICE_ACCOUNT identity."""
    import asyncio

    from e2eai.delegated_identity import AuthMode, DelegatedExecutor, DelegatedIdentityContext
    from e2eai.mcp_tool_call import MCPToolCallRecord, OfflineExecutor

    ctx = DelegatedIdentityContext(
        user_id="svc-admin",
        system_id="hr-system",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
    )
    inner = OfflineExecutor()
    executor = DelegatedExecutor(inner=inner, identity=ctx)

    record = MCPToolCallRecord(
        system_id="hr-system",
        operation_id="list_employees",
        method="GET",
        path="/employees",
        read_only=True,
        needs_confirmation=False,
        tool_description="List employees",
        match_score=0.8,
    )

    with pytest.raises(ValueError, match="[Ss]ervice.account.*not.*allowed|[Dd]elegated.*identity.*required"):
        asyncio.run(executor.execute(record))


def test_delegated_executor_succeeds_with_valid_identity():
    """DelegatedExecutor must pass through to inner executor with valid delegated identity."""
    import asyncio

    from e2eai.delegated_identity import AuthMode, DelegatedExecutor, DelegatedIdentityContext
    from e2eai.mcp_tool_call import MCPToolCallRecord, OfflineExecutor

    ctx = DelegatedIdentityContext(
        user_id="user-123",
        system_id="hr-system",
        auth_mode=AuthMode.TOKEN_EXCHANGE,
    )
    inner = OfflineExecutor(results={"list_employees": {"record_count": 5}})
    executor = DelegatedExecutor(inner=inner, identity=ctx)

    record = MCPToolCallRecord(
        system_id="hr-system",
        operation_id="list_employees",
        method="GET",
        path="/employees",
        read_only=True,
        needs_confirmation=False,
        tool_description="List employees",
        match_score=0.8,
    )

    result = asyncio.run(executor.execute(record))
    assert result["record_count"] == 5
    assert result.get("status") in ("offline", "ok", None) or "record_count" in result


# ---------------------------------------------------------------------------
# DB persistence: auth_mode + acting_user_id in McpToolCall
# ---------------------------------------------------------------------------


def test_execute_and_persist_with_identity_stores_auth_metadata():
    """FR-X3: execute_and_persist_tool_calls with identity_context stores auth_mode and acting_user_id."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            AuditEntry, Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, McpToolCall, Message, MessageCitation, User, sessions,
        )
        from e2eai.delegated_identity import AuthMode, DelegatedExecutor, DelegatedIdentityContext
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

            identity = DelegatedIdentityContext(
                user_id=str(andi.id),
                system_id="hr-system",
                auth_mode=AuthMode.TOKEN_EXCHANGE,
            )
            inner = OfflineExecutor(results={"list_employees": {"record_count": 5}})
            executor = DelegatedExecutor(inner=inner, identity=identity)

            conv = await create_conversation(session, user=andi, title="FR-X3 test")
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees are there?",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            tc_rows = (await session.execute(
                select(McpToolCall).where(McpToolCall.message_id == asst_msg.id)
            )).scalars().all()
            assert len(tc_rows) >= 1

            tc = next((t for t in tc_rows if t.operation_id == "list_employees"), None)
            assert tc is not None
            assert tc.auth_mode == "token_exchange"
            assert tc.acting_user_id == str(andi.id)

            # Verify audit records include auth mode metadata
            audit_rows = (await session.execute(
                select(AuditEntry).where(
                    AuditEntry.action == "mcp.tool_call.executed"
                )
            )).scalars().all()
            assert len(audit_rows) >= 1
            latest_audit = audit_rows[-1]
            assert latest_audit.details.get("auth_mode") == "token_exchange"
            assert latest_audit.details.get("acting_user_id") == str(andi.id)
            # Never store token values in audit
            audit_str = str(latest_audit.details).lower()
            assert "bearer" not in audit_str
            assert "secret" not in audit_str
            assert "token_value" not in audit_str

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_service_account_executor_blocked_in_pipeline():
    """FR-X3: DelegatedExecutor with SERVICE_ACCOUNT must not execute any tool calls."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, McpToolCall, Message, MessageCitation, User, sessions,
        )
        from e2eai.delegated_identity import AuthMode, DelegatedExecutor, DelegatedIdentityContext
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

            # SERVICE_ACCOUNT should be blocked
            identity = DelegatedIdentityContext(
                user_id="svc-admin",
                system_id="hr-system",
                auth_mode=AuthMode.SERVICE_ACCOUNT,
            )
            inner = OfflineExecutor()
            executor = DelegatedExecutor(inner=inner, identity=identity)

            conv = await create_conversation(session, user=andi, title="FR-X3 blocked test")

            # The executor should raise on each tool call, but the pipeline should
            # record the failure safely rather than crashing the whole request
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees are there?",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
            )

            # Tool calls should show as rejected, not executed
            for tc in result.get("tool_calls", []):
                assert tc["status"] in ("rejected_service_account", "error"), \
                    f"Expected rejected status, got {tc['status']}"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_mcp_tool_call_without_identity_backward_compatible():
    """FR-X3: existing callers without identity_context should still work (auth_mode=None)."""
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
                text="There are 10 employees.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

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

            conv = await create_conversation(session, user=andi, title="Backward compat")
            # No identity context — existing behavior
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="How many employees?",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=OfflineExecutor(),
            )

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            tc_rows = (await session.execute(
                select(McpToolCall).where(McpToolCall.message_id == asst_msg.id)
            )).scalars().all()
            assert len(tc_rows) >= 1
            for tc in tc_rows:
                # auth_mode and acting_user_id should be None for backward compat
                assert tc.auth_mode is None
                assert tc.acting_user_id is None

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_mcp_tool_call_db_rows_never_contain_tokens():
    """FR-X3: McpToolCall rows with delegated identity must never store raw token values."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import (
            Chunk, ChunkEmbedding, Conversation, DocPrincipal,
            Document, DocumentVersion, Folder, McpToolCall, Message, MessageCitation, User, sessions,
        )
        from e2eai.delegated_identity import AuthMode, DelegatedExecutor, DelegatedIdentityContext
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
                title="HR Policy", text="Employee benefits doc.", page=1,
            )
            await share_document(session, _Authz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=_Embedder(), document_id=doc.id)

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

            identity = DelegatedIdentityContext(
                user_id=str(andi.id),
                system_id="hr-system",
                auth_mode=AuthMode.DELEGATED,
            )
            inner = OfflineExecutor(results={
                "list_employees": {
                    "record_count": 3,
                    "authorization": "Bearer super-secret-token-xyz",
                    "server_url": "https://internal.hr.example.local",
                },
            })
            executor = DelegatedExecutor(inner=inner, identity=identity)

            conv = await create_conversation(session, user=andi, title="Token leak test")
            await send_message(
                session, user=andi, conversation_id=conv.id,
                question="List employees with bearer token secret-key-abc",
                embedder=_Embedder(),
                descriptors=[hr_desc],
                executor=executor,
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
                    "auth_mode": tc.auth_mode, "acting_user_id": tc.acting_user_id,
                }).lower()
                assert "super-secret-token-xyz" not in row_str
                assert "secret-key-abc" not in row_str
                assert "internal.hr.example.local" not in row_str
                assert "bearer token" not in row_str

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Route wiring: delegated identity API endpoint
# ---------------------------------------------------------------------------


def test_delegated_identity_route_is_wired():
    """POST /api/v1/systems/{system_id}/delegated-identity/validate is registered."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/systems/{system_id}/delegated-identity/validate" in openapi["paths"], (
        f"Route not found. Registered paths: {sorted(openapi['paths'].keys())}"
    )
