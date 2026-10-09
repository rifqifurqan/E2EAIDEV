"""P1 release gates: eval thresholds, zero permission leaks, red-team pass, human sign-off (FR-RL2).

Gates block a production release unless all configured checks pass. Failed gates do not mutate
production_bundle_id or supersede the current production bundle. Stored audit metadata is safe:
no raw eval prompts, responses, restricted content, secrets, or snippets.
"""

import asyncio
import subprocess
import uuid

from sqlalchemy import delete, func, select

from e2eai.bot_release import (
    ReleaseGatePolicy,
    check_release_gates,
    create_bot,
    release_bundle,
)
from e2eai.db import (
    Bot,
    BotBundle,
    BotGrant,
    BotScope,
    Chunk,
    ChunkEmbedding,
    DocPrincipal,
    Document,
    DocumentVersion,
    EvalRun,
    Folder,
    Team,
    TeamMember,
    User,
    sessions,
)
from e2eai.seed import seed_demo


async def _reset(session):
    for model in (BotScope, BotGrant, BotBundle, Bot, EvalRun, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder, TeamMember, Team):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return owner, andi


async def _seed_eval_run(session, *, adapter: str, metrics: dict, created_by: str) -> EvalRun:
    """Insert a fake EvalRun record for gate checking."""
    run = EvalRun(
        adapter=adapter,
        status="completed",
        metrics=metrics,
        item_results=[],
        created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


# ---------- 1. check_release_gates with all gates passing ----------

def test_all_gates_pass_when_eval_and_leak_and_redteam_and_signoff_are_satisfied():
    """When recent eval runs meet thresholds, leak count is zero, red-team passes, and
    human sign-off is True, all gates pass and overall verdict is True."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)

            # Seed passing eval runs
            await _seed_eval_run(session, adapter="ragas.local", metrics={"answer_correctness": 0.85}, created_by=f"user:{owner.id}")
            await _seed_eval_run(session, adapter="permission-leak.local", metrics={"leaks": 0, "probes": 10, "leak_rate": 0.0}, created_by=f"user:{owner.id}")
            await _seed_eval_run(session, adapter="security-red-team.local", metrics={"pass_rate": 1.0, "leaks": 0, "items": 20}, created_by=f"user:{owner.id}")

            policy = ReleaseGatePolicy(
                eval_threshold=0.8,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
                require_zero_leaks=True,
                redteam_pass_rate=0.95,
                require_human_signoff=True,
            )

            result = check_release_gates(
                eval_runs=[
                    {"adapter": "ragas.local", "metrics": {"answer_correctness": 0.85}},
                    {"adapter": "permission-leak.local", "metrics": {"leaks": 0, "probes": 10, "leak_rate": 0.0}},
                    {"adapter": "security-red-team.local", "metrics": {"pass_rate": 1.0, "leaks": 0, "items": 20}},
                ],
                policy=policy,
                human_signoff=True,
            )

            assert result["passed"] is True
            assert result["gates"]["eval_threshold"]["passed"] is True
            assert result["gates"]["zero_permission_leaks"]["passed"] is True
            assert result["gates"]["redteam_pass"]["passed"] is True
            assert result["gates"]["human_signoff"]["passed"] is True

    _migrate()
    asyncio.run(run())


# ---------- 2. eval threshold gate fails ----------

def test_eval_threshold_gate_fails_when_metric_below_threshold():
    """Eval threshold gate fails when the eval metric is below the configured threshold."""
    async def run():
        async with sessions()() as session:
            await _reset(session)

            policy = ReleaseGatePolicy(
                eval_threshold=0.8,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
            )

            result = check_release_gates(
                eval_runs=[
                    {"adapter": "ragas.local", "metrics": {"answer_correctness": 0.65}},
                ],
                policy=policy,
                human_signoff=False,
            )

            assert result["passed"] is False
            assert result["gates"]["eval_threshold"]["passed"] is False
            assert result["gates"]["eval_threshold"]["actual"] == 0.65
            assert result["gates"]["eval_threshold"]["required"] == 0.8

    _migrate()
    asyncio.run(run())


# ---------- 3. permission leak gate fails ----------

def test_permission_leak_gate_fails_when_leaks_nonzero():
    """Zero permission leaks gate fails when the leak suite found leaks."""
    async def run():
        async with sessions()() as session:
            await _reset(session)

            policy = ReleaseGatePolicy(require_zero_leaks=True)

            result = check_release_gates(
                eval_runs=[
                    {"adapter": "permission-leak.local", "metrics": {"leaks": 2, "probes": 10, "leak_rate": 0.2}},
                ],
                policy=policy,
                human_signoff=False,
            )

            assert result["passed"] is False
            assert result["gates"]["zero_permission_leaks"]["passed"] is False
            assert result["gates"]["zero_permission_leaks"]["leaks"] == 2

    _migrate()
    asyncio.run(run())


# ---------- 4. red-team gate fails ----------

def test_redteam_gate_fails_when_pass_rate_below_threshold():
    """Red-team gate fails when the security red-team pass rate is below threshold."""
    async def run():
        async with sessions()() as session:
            await _reset(session)

            policy = ReleaseGatePolicy(redteam_pass_rate=0.95)

            result = check_release_gates(
                eval_runs=[
                    {"adapter": "security-red-team.local", "metrics": {"pass_rate": 0.80, "leaks": 1, "items": 20}},
                ],
                policy=policy,
                human_signoff=False,
            )

            assert result["passed"] is False
            assert result["gates"]["redteam_pass"]["passed"] is False
            assert result["gates"]["redteam_pass"]["actual"] == 0.80
            assert result["gates"]["redteam_pass"]["required"] == 0.95

    _migrate()
    asyncio.run(run())


# ---------- 5. human sign-off gate fails ----------

def test_human_signoff_gate_fails_when_not_signed_off():
    """Human sign-off gate fails when human_signoff is False and policy requires it."""
    async def run():
        async with sessions()() as session:
            await _reset(session)

            policy = ReleaseGatePolicy(require_human_signoff=True)

            result = check_release_gates(
                eval_runs=[],
                policy=policy,
                human_signoff=False,
            )

            assert result["passed"] is False
            assert result["gates"]["human_signoff"]["passed"] is False

    _migrate()
    asyncio.run(run())


# ---------- 6. release_bundle with gates blocks on failed gate ----------

def test_release_bundle_blocked_by_failed_gate_does_not_mutate_production():
    """When release gates fail, release_bundle raises AppError and does not change
    production_bundle_id or supersede the current production bundle."""
    async def run():
        from e2eai.core.errors import AppError

        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)

            bot = await create_bot(session, owner=owner, name="Gated Bot")
            v1 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            assert v1.status == "production"

            # Attempt gated release with failing eval threshold
            policy = ReleaseGatePolicy(eval_threshold=0.9, eval_adapter="ragas.local", eval_metric="answer_correctness")
            eval_runs = [{"adapter": "ragas.local", "metrics": {"answer_correctness": 0.5}}]

            try:
                await release_bundle(
                    session, actor=owner, bot_id=bot.id, bundle={"prompt": "v2"},
                    gate_policy=policy, gate_eval_runs=eval_runs, gate_human_signoff=False,
                )
                assert False, "Should have raised AppError"
            except AppError as exc:
                assert exc.status == 422
                assert "gate" in exc.title.lower() or "release" in exc.title.lower()

            # v1 must still be production, not superseded
            await session.refresh(v1)
            assert v1.status == "production"
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == v1.id

            # No v2 bundle should exist
            from sqlalchemy import select as sel
            count = await session.scalar(sel(func.count()).select_from(BotBundle).where(BotBundle.bot_id == bot.id))
            assert count == 1  # only v1

    _migrate()
    asyncio.run(run())


# ---------- 7. release_bundle with gates succeeds when all pass ----------

def test_release_bundle_succeeds_when_all_gates_pass():
    """When all gates pass, release_bundle proceeds normally and supersedes the old bundle."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)

            bot = await create_bot(session, owner=owner, name="Gated Bot OK")
            v1 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})

            policy = ReleaseGatePolicy(
                eval_threshold=0.7,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
                require_zero_leaks=True,
                redteam_pass_rate=0.9,
                require_human_signoff=True,
            )
            eval_runs = [
                {"adapter": "ragas.local", "metrics": {"answer_correctness": 0.85}},
                {"adapter": "permission-leak.local", "metrics": {"leaks": 0, "probes": 5, "leak_rate": 0.0}},
                {"adapter": "security-red-team.local", "metrics": {"pass_rate": 1.0, "leaks": 0, "items": 10}},
            ]

            v2 = await release_bundle(
                session, actor=owner, bot_id=bot.id, bundle={"prompt": "v2"},
                gate_policy=policy, gate_eval_runs=eval_runs, gate_human_signoff=True,
            )

            assert v2.version == 2
            assert v2.status == "production"
            await session.refresh(v1)
            assert v1.status == "superseded"
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == v2.id

    _migrate()
    asyncio.run(run())


# ---------- 8. backward compatibility: release without gates ----------

def test_release_bundle_without_gates_works_unchanged():
    """Calling release_bundle without gate_policy works exactly as before (backward compat)."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)

            bot = await create_bot(session, owner=owner, name="No Gates Bot")
            v1 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            v2 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v2"})
            assert v2.version == 2
            assert v2.status == "production"
            await session.refresh(v1)
            assert v1.status == "superseded"

    _migrate()
    asyncio.run(run())


# ---------- 9. audit metadata is safe ----------

def test_gate_audit_metadata_contains_no_raw_eval_content():
    """Gate result stored in audit contains only gate names, thresholds, pass/fail booleans,
    and safe numeric values — never raw eval prompts, responses, or restricted content."""
    async def run():
        from e2eai.db import AuditEntry

        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)

            bot = await create_bot(session, owner=owner, name="Audit Gate Bot")

            policy = ReleaseGatePolicy(
                eval_threshold=0.7,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
                require_zero_leaks=True,
                redteam_pass_rate=0.9,
                require_human_signoff=True,
            )
            eval_runs = [
                {"adapter": "ragas.local", "metrics": {"answer_correctness": 0.85}},
                {"adapter": "permission-leak.local", "metrics": {"leaks": 0, "probes": 5, "leak_rate": 0.0}},
                {"adapter": "security-red-team.local", "metrics": {"pass_rate": 1.0, "leaks": 0, "items": 10}},
            ]

            v1 = await release_bundle(
                session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"},
                gate_policy=policy, gate_eval_runs=eval_runs, gate_human_signoff=True,
            )

            # Find the gate audit entry
            gate_audit = await session.scalar(
                select(AuditEntry).where(
                    AuditEntry.action == "bot.bundle.release",
                    AuditEntry.target == f"bot:{bot.id}",
                ).order_by(AuditEntry.seq.desc())
            )
            assert gate_audit is not None
            details = gate_audit.details

            # Must contain gates_passed
            assert details.get("gates_passed") is True

            # Serialized details must not contain raw eval content
            import json
            serialized = json.dumps(details).lower()
            for forbidden in ("prompt", "response", "answer", "secret", "30 percent", "revenue", "whatsapp"):
                assert forbidden not in serialized, f"Forbidden term '{forbidden}' found in audit details"

    _migrate()
    asyncio.run(run())


# ---------- 10. release_bundle loads completed DB eval runs when not passed explicitly ----------

def test_release_bundle_with_gate_policy_uses_completed_db_eval_runs_by_default():
    """A gated release should use existing completed EvalRun rows when the caller does
    not pass explicit gate_eval_runs. This keeps the API path usable without trusting
    client-supplied eval summaries."""
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi = await _users(session)
            await _seed_eval_run(session, adapter="ragas.local", metrics={"answer_correctness": 0.85}, created_by=f"user:{owner.id}")
            await _seed_eval_run(session, adapter="permission-leak.local", metrics={"leaks": 0, "probes": 10, "leak_rate": 0.0}, created_by=f"user:{owner.id}")
            await _seed_eval_run(session, adapter="security-red-team.local", metrics={"pass_rate": 1.0, "leaks": 0, "items": 20}, created_by=f"user:{owner.id}")

            bot = await create_bot(session, owner=owner, name="DB Gates Bot")
            policy = ReleaseGatePolicy(
                eval_threshold=0.8,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
                require_zero_leaks=True,
                redteam_pass_rate=0.95,
                require_human_signoff=True,
            )

            released = await release_bundle(
                session,
                actor=owner,
                bot_id=bot.id,
                bundle={"prompt": "v1"},
                gate_policy=policy,
                gate_human_signoff=True,
            )

            assert released.status == "production"
            assert released.version == 1

    _migrate()
    asyncio.run(run())


# ---------- 11. API body can carry release gates and sign-off ----------

def test_bundle_request_body_parses_release_gates_without_raw_eval_payloads():
    """The release API accepts gate policy fields + human sign-off, not raw eval
    prompts/responses or client-supplied eval content."""
    from e2eai.bot_release import BundleIn

    body = BundleIn(
        bundle={"prompt": "v1"},
        release_gates={
            "eval_threshold": 0.8,
            "eval_adapter": "ragas.local",
            "eval_metric": "answer_correctness",
            "require_zero_leaks": True,
            "redteam_pass_rate": 0.95,
            "require_human_signoff": True,
        },
        human_signoff=True,
    )

    assert body.release_gates is not None
    assert body.release_gates.to_policy().require_zero_leaks is True
    assert body.release_gates.to_policy().redteam_pass_rate == 0.95
    assert body.human_signoff is True


# ---------- 12. missing eval run for a configured gate ----------

def test_gate_fails_when_required_eval_run_missing():
    """If policy requires an eval threshold but no matching eval run is provided, the gate fails."""
    async def run():
        async with sessions()() as session:
            await _reset(session)

            policy = ReleaseGatePolicy(
                eval_threshold=0.8,
                eval_adapter="ragas.local",
                eval_metric="answer_correctness",
            )

            result = check_release_gates(
                eval_runs=[],  # no eval runs at all
                policy=policy,
                human_signoff=False,
            )

            assert result["passed"] is False
            assert result["gates"]["eval_threshold"]["passed"] is False

    _migrate()
    asyncio.run(run())
