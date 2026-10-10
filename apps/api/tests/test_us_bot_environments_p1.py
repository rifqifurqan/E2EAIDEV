"""P1 environments: dev -> staging -> prod promotion model, with Lite single-environment mode (FR-RL6).

A bot bundle is created once (immutable) and promoted between environments; promotion repoints an
environment at that immutable bundle and never edits the prod bundle in place. Staging/prod promotion
can require that environment's release gates plus human sign-off. Lite tier keeps a single environment
where the existing release_bundle / production_bundle_id path still applies (backward compatible).
Stored audit metadata is safe: environment/version/gate names only, never raw eval payloads.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.bot_release import (
    ENVIRONMENTS,
    ReleaseGatePolicy,
    create_bot,
    promote_bundle,
    release_bundle,
    release_to_environment,
)
from e2eai.db import (
    Bot,
    BotBundle,
    BotEnvironment,
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
    for model in (BotEnvironment, BotScope, BotGrant, BotBundle, Bot, EvalRun, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder, TeamMember, Team):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    return owner


async def _seed_eval_run(session, *, adapter, metrics, created_by):
    run = EvalRun(adapter=adapter, status="completed", metrics=metrics, item_results=[], created_by=created_by)
    session.add(run)
    await session.commit()
    return run


async def _env_bundle_id(session, bot_id, environment):
    return await session.scalar(
        select(BotEnvironment.bundle_id).where(
            BotEnvironment.bot_id == bot_id, BotEnvironment.environment == environment
        )
    )


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


# ---------- 1. dev -> staging -> prod promotes the same immutable bundle ----------

def test_promotion_points_same_immutable_bundle_through_environments():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _users(session)
            bot = await create_bot(session, owner=owner, name="Pipeline Bot")

            dev = await release_to_environment(
                session, actor=owner, bot_id=bot.id,
                bundle={"prompt": "v1", "model": "qwen", "index": "idx-dev"}, environment="dev",
            )
            assert await _env_bundle_id(session, bot.id, "dev") == dev.id

            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="dev", target_env="staging")
            assert await _env_bundle_id(session, bot.id, "staging") == dev.id

            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod")
            assert await _env_bundle_id(session, bot.id, "prod") == dev.id

            # prod answer path reflects the promoted bundle
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == dev.id

            # the bundle content was never edited in place
            after = await session.get(BotBundle, dev.id)
            assert after.bundle == {"prompt": "v1", "model": "qwen", "index": "idx-dev"}
            assert ENVIRONMENTS == ("dev", "staging", "prod")

    _migrate()
    asyncio.run(run())


# ---------- 2. promotion to prod can require gates + sign-off ----------

def test_promote_to_prod_requires_release_gates_and_signoff():
    async def run():
        from e2eai.core.errors import AppError

        async with sessions()() as session:
            await _reset(session)
            owner = await _users(session)
            await _seed_eval_run(session, adapter="ragas.local", metrics={"answer_correctness": 0.85}, created_by=f"user:{owner.id}")
            await _seed_eval_run(session, adapter="permission-leak.local", metrics={"leaks": 0, "probes": 10, "leak_rate": 0.0}, created_by=f"user:{owner.id}")

            bot = await create_bot(session, owner=owner, name="Gated Promote Bot")
            await release_to_environment(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"}, environment="dev")
            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="dev", target_env="staging")

            policy = ReleaseGatePolicy(
                eval_threshold=0.8, eval_adapter="ragas.local", eval_metric="answer_correctness",
                require_zero_leaks=True, require_human_signoff=True,
            )

            # sign-off missing -> blocked, prod not touched
            try:
                await promote_bundle(
                    session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod",
                    gate_policy=policy, gate_human_signoff=False,
                )
                assert False, "should have raised"
            except AppError as exc:
                assert exc.status == 422
            assert await _env_bundle_id(session, bot.id, "prod") is None
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id is None

            # gates + sign-off pass -> promoted
            staged = await _env_bundle_id(session, bot.id, "staging")
            await promote_bundle(
                session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod",
                gate_policy=policy, gate_human_signoff=True,
            )
            assert await _env_bundle_id(session, bot.id, "prod") == staged
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == staged

    _migrate()
    asyncio.run(run())


# ---------- 3. promoting a new bundle to prod never edits the old prod bundle in place ----------

def test_promotion_never_edits_prod_bundle_in_place():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _users(session)
            bot = await create_bot(session, owner=owner, name="Immutable Prod Bot")

            a = await release_to_environment(session, actor=owner, bot_id=bot.id, bundle={"prompt": "A"}, environment="dev")
            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="dev", target_env="staging")
            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod")

            b = await release_to_environment(session, actor=owner, bot_id=bot.id, bundle={"prompt": "B"}, environment="dev")
            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="dev", target_env="staging")
            await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod")

            # old prod bundle still exists, unchanged
            old = await session.get(BotBundle, a.id)
            assert old is not None
            assert old.bundle == {"prompt": "A"}
            assert a.id != b.id

            # prod now points at the new immutable bundle
            assert await _env_bundle_id(session, bot.id, "prod") == b.id
            bot = await session.get(Bot, bot.id)
            assert bot.production_bundle_id == b.id

    _migrate()
    asyncio.run(run())


# ---------- 4. promotion order is enforced; empty source cannot be promoted ----------

def test_promotion_path_and_source_are_validated():
    async def run():
        from e2eai.core.errors import AppError

        async with sessions()() as session:
            await _reset(session)
            owner = await _users(session)
            bot = await create_bot(session, owner=owner, name="Order Bot")
            await release_to_environment(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"}, environment="dev")

            # skipping staging is rejected
            try:
                await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="dev", target_env="prod")
                assert False, "should reject skip"
            except AppError as exc:
                assert exc.status in (400, 422)

            # promoting from an empty environment is rejected
            try:
                await promote_bundle(session, actor=owner, bot_id=bot.id, source_env="staging", target_env="prod")
                assert False, "should reject empty source"
            except AppError as exc:
                assert exc.status in (404, 409)

    _migrate()
    asyncio.run(run())


# ---------- 5. Lite single-environment mode is backward compatible ----------

def test_lite_single_environment_backward_compatible():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner = await _users(session)

            # existing release_bundle path unchanged (versions + supersede)
            bot = await create_bot(session, owner=owner, name="Lite Bot")
            v1 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v1"})
            v2 = await release_bundle(session, actor=owner, bot_id=bot.id, bundle={"prompt": "v2"})
            assert v2.version == 2 and v2.status == "production"
            await session.refresh(v1)
            assert v1.status == "superseded"

            # Lite simplified mode: release straight to prod (single environment) sets production pointer
            lite = await create_bot(session, owner=owner, name="Lite Single Env")
            direct = await release_to_environment(session, actor=owner, bot_id=lite.id, bundle={"prompt": "only"}, environment="prod")
            assert await _env_bundle_id(session, lite.id, "prod") == direct.id
            lite = await session.get(Bot, lite.id)
            assert lite.production_bundle_id == direct.id

    _migrate()
    asyncio.run(run())


# ---------- 6. API bodies carry only environment/gate/sign-off fields, no raw eval payloads ----------

def test_api_bodies_carry_environment_and_gate_fields_only():
    from e2eai.bot_release import EnvironmentReleaseIn, PromoteIn

    rel = EnvironmentReleaseIn(bundle={"prompt": "v1"}, environment="dev")
    assert rel.environment == "dev"

    promo = PromoteIn(
        source_env="staging",
        target_env="prod",
        release_gates={"require_zero_leaks": True, "require_human_signoff": True},
        human_signoff=True,
        allow_production_data=False,
    )
    assert promo.source_env == "staging" and promo.target_env == "prod"
    assert promo.release_gates.to_policy().require_zero_leaks is True
    assert promo.human_signoff is True
    # no raw eval payload fields exist on the promotion request
    assert not hasattr(promo, "eval_runs")
    assert "eval_runs" not in promo.model_dump()
