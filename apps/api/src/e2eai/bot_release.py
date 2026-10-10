"""Versioned bot bundles, release gates, and bot-scoped permission-aware answering (FR-RL1, FR-RL2, FR-RL5, FR-RL7)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .authz import principals
from .core.errors import AppError
from .db import Bot, BotBundle, BotEnvironment, BotGrant, BotScope, EvalRun, User, get_session
from .retrieval import Embedder, LiteLLMEmbedder, answer_question


# ---------------------------------------------------------------------------
# FR-RL2  Release gate policy and checker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseGatePolicy:
    """Configurable release gates per bot (FR-RL2).

    Each field is optional; gates that are not configured are skipped.
    """

    # Eval threshold gate: require a metric on a specific adapter >= threshold
    eval_threshold: float | None = None
    eval_adapter: str = "ragas.local"
    eval_metric: str = "answer_correctness"

    # Permission leak gate: require zero leaks
    require_zero_leaks: bool = False

    # Red-team gate: require pass_rate >= threshold
    redteam_pass_rate: float | None = None

    # Human sign-off gate
    require_human_signoff: bool = False


def _find_run(eval_runs: Sequence[dict], adapter: str) -> dict | None:
    """Find the latest (last) eval run dict matching the adapter name."""
    matched = None
    for run in eval_runs:
        if run.get("adapter") == adapter:
            matched = run
    return matched


def check_release_gates(
    *,
    eval_runs: Sequence[dict],
    policy: ReleaseGatePolicy,
    human_signoff: bool = False,
) -> dict:
    """Evaluate all configured release gates and return a verdict (FR-RL2).

    Returns a dict with ``passed`` (bool) and ``gates`` (per-gate detail).
    Stored metadata is safe: only gate names, thresholds, pass/fail booleans,
    and numeric values — never raw eval content, prompts, or responses.
    """
    gates: dict[str, dict] = {}

    # --- eval threshold ---
    if policy.eval_threshold is not None:
        run = _find_run(eval_runs, policy.eval_adapter)
        actual = (run.get("metrics") or {}).get(policy.eval_metric) if run else None
        passed = actual is not None and float(actual) >= policy.eval_threshold
        gates["eval_threshold"] = {
            "passed": passed,
            "actual": actual,
            "required": policy.eval_threshold,
            "adapter": policy.eval_adapter,
            "metric": policy.eval_metric,
        }

    # --- zero permission leaks ---
    if policy.require_zero_leaks:
        run = _find_run(eval_runs, "permission-leak.local")
        leaks = (run.get("metrics") or {}).get("leaks") if run else None
        passed = leaks is not None and int(leaks) == 0
        gates["zero_permission_leaks"] = {
            "passed": passed,
            "leaks": int(leaks) if leaks is not None else None,
        }

    # --- red-team pass rate ---
    if policy.redteam_pass_rate is not None:
        run = _find_run(eval_runs, "security-red-team.local")
        actual = (run.get("metrics") or {}).get("pass_rate") if run else None
        passed = actual is not None and float(actual) >= policy.redteam_pass_rate
        gates["redteam_pass"] = {
            "passed": passed,
            "actual": float(actual) if actual is not None else None,
            "required": policy.redteam_pass_rate,
        }

    # --- human sign-off ---
    if policy.require_human_signoff:
        gates["human_signoff"] = {"passed": bool(human_signoff)}

    overall = all(g["passed"] for g in gates.values()) if gates else True
    return {"passed": overall, "gates": gates}


async def create_bot(session: AsyncSession, *, owner: User, name: str) -> Bot:
    if not name.strip():
        raise AppError(400, "Bot name is required")
    bot = Bot(name=name, owner_id=owner.id)
    session.add(bot)
    await session.flush()
    await audit.record(session, f"user:{owner.id}", "bot.create", f"bot:{bot.id}", {"name": name})
    await session.commit()
    return bot


async def _load_release_gate_eval_runs(session: AsyncSession) -> list[dict]:
    """Load completed EvalRun summaries for release gates.

    The API/service path should evaluate gates from server-side EvalRun rows, not
    from client-supplied raw eval payloads. Only safe summary fields are returned.
    """
    runs = (await session.execute(
        select(EvalRun)
        .where(EvalRun.status == "completed")
        .order_by(EvalRun.created_at.asc(), EvalRun.id.asc())
    )).scalars().all()
    return [
        {
            "id": str(run.id),
            "adapter": run.adapter,
            "metrics": dict(run.metrics or {}),
            "status": run.status,
        }
        for run in runs
    ]


async def release_bundle(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    bundle: dict,
    gate_policy: ReleaseGatePolicy | None = None,
    gate_eval_runs: Sequence[dict] | None = None,
    gate_human_signoff: bool = False,
) -> BotBundle:
    bot = await _load_bot(session, bot_id)

    # FR-RL2: check release gates before mutating any state
    gate_result: dict | None = None
    if gate_policy is not None:
        eval_runs = list(gate_eval_runs) if gate_eval_runs is not None else await _load_release_gate_eval_runs(session)
        gate_result = check_release_gates(
            eval_runs=eval_runs,
            policy=gate_policy,
            human_signoff=gate_human_signoff,
        )
        if not gate_result["passed"]:
            failed_names = [name for name, g in gate_result["gates"].items() if not g["passed"]]
            await audit.record(
                session,
                f"user:{actor.id}",
                "bot.bundle.release.blocked",
                f"bot:{bot_id}",
                {"gates_passed": False, "failed_gates": failed_names},
            )
            await session.commit()
            raise AppError(
                422,
                "Release blocked by failed gates",
                f"Failed gates: {', '.join(failed_names)}",
            )

    current = await session.get(BotBundle, bot.production_bundle_id) if bot.production_bundle_id else None
    if current:
        current.status = "superseded"
    version = (await session.scalar(select(func.max(BotBundle.version)).where(BotBundle.bot_id == bot_id))) or 0
    released = BotBundle(
        bot_id=bot_id,
        version=version + 1,
        status="production",
        bundle=dict(bundle),
        released_by=str(actor.id),
    )
    session.add(released)
    await session.flush()
    bot.production_bundle_id = released.id

    audit_details: dict = {"version": released.version}
    if gate_result is not None:
        audit_details["gates_passed"] = True
        audit_details["gate_count"] = len(gate_result["gates"])
    await audit.record(session, f"user:{actor.id}", "bot.bundle.release", f"bot:{bot_id}", audit_details)
    await session.commit()
    return released


async def rollback_bundle(session: AsyncSession, *, actor: User, bot_id: uuid.UUID, target_bundle_id: uuid.UUID) -> BotBundle:
    bot = await _load_bot(session, bot_id)
    target = await session.get(BotBundle, target_bundle_id)
    if target is None or target.bot_id != bot_id:
        raise AppError(404, "Bundle not found")
    current = await session.get(BotBundle, bot.production_bundle_id) if bot.production_bundle_id else None
    if current and current.id != target.id:
        current.status = "rolled_back"
    target.status = "production"
    bot.production_bundle_id = target.id
    await audit.record(session, f"user:{actor.id}", "bot.bundle.rollback", f"bot:{bot_id}", {"target_version": target.version})
    await session.commit()
    return target


# ---------------------------------------------------------------------------
# FR-RL6  Environments: dev -> staging -> prod promotion (Lite = single env)
# ---------------------------------------------------------------------------

ENVIRONMENTS: tuple[str, ...] = ("dev", "staging", "prod")


def _check_environment(environment: str) -> None:
    if environment not in ENVIRONMENTS:
        raise AppError(400, "Unknown environment", f"Valid environments: {', '.join(ENVIRONMENTS)}")


async def _set_env_pointer(
    session: AsyncSession,
    *,
    bot_id: uuid.UUID,
    environment: str,
    bundle_id: uuid.UUID,
    allow_production_data: bool | None = None,
) -> None:
    row = await session.get(BotEnvironment, (bot_id, environment))
    if row is None:
        row = BotEnvironment(bot_id=bot_id, environment=environment)
        session.add(row)
    row.bundle_id = bundle_id
    if allow_production_data is not None:
        row.allow_production_data = allow_production_data


async def release_to_environment(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    bundle: dict,
    environment: str = "dev",
) -> BotBundle:
    """Create an immutable bundle version and point one environment at it (FR-RL6).

    Default target is ``dev``. Lite tier may release straight to ``prod`` (single environment).
    Releasing to prod also updates ``production_bundle_id`` so the answer path reflects prod.
    """
    _check_environment(environment)
    bot = await _load_bot(session, bot_id)
    version = (await session.scalar(select(func.max(BotBundle.version)).where(BotBundle.bot_id == bot_id))) or 0
    created = BotBundle(
        bot_id=bot_id,
        version=version + 1,
        status="draft",
        bundle=dict(bundle),
        released_by=str(actor.id),
    )
    session.add(created)
    await session.flush()
    await _set_env_pointer(session, bot_id=bot_id, environment=environment, bundle_id=created.id)
    if environment == "prod":
        bot.production_bundle_id = created.id
    await audit.record(
        session, f"user:{actor.id}", "bot.env.release", f"bot:{bot_id}",
        {"environment": environment, "version": created.version},
    )
    await session.commit()
    return created


async def promote_bundle(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    source_env: str,
    target_env: str,
    gate_policy: ReleaseGatePolicy | None = None,
    gate_eval_runs: Sequence[dict] | None = None,
    gate_human_signoff: bool = False,
    allow_production_data: bool = False,
) -> BotBundle:
    """Promote the immutable bundle in ``source_env`` to ``target_env`` (FR-RL6).

    Promotion only follows the chain dev -> staging -> prod and repoints the target environment at
    the same immutable bundle — it never edits the prod bundle in place. Staging/prod promotion can
    require that environment's release gates plus human sign-off; a failed gate changes nothing.
    """
    _check_environment(source_env)
    _check_environment(target_env)
    if ENVIRONMENTS.index(target_env) != ENVIRONMENTS.index(source_env) + 1:
        raise AppError(400, "Invalid promotion path", f"Promote in order: {' -> '.join(ENVIRONMENTS)}")

    bot = await _load_bot(session, bot_id)
    source = await session.get(BotEnvironment, (bot_id, source_env))
    if source is None or source.bundle_id is None:
        raise AppError(409, "Nothing to promote", f"No bundle deployed in {source_env}")
    bundle_id = source.bundle_id

    gate_result: dict | None = None
    if gate_policy is not None:
        eval_runs = list(gate_eval_runs) if gate_eval_runs is not None else await _load_release_gate_eval_runs(session)
        gate_result = check_release_gates(eval_runs=eval_runs, policy=gate_policy, human_signoff=gate_human_signoff)
        if not gate_result["passed"]:
            failed_names = [name for name, g in gate_result["gates"].items() if not g["passed"]]
            await audit.record(
                session, f"user:{actor.id}", "bot.env.promote.blocked", f"bot:{bot_id}",
                {"source": source_env, "target": target_env, "gates_passed": False, "failed_gates": failed_names},
            )
            await session.commit()
            raise AppError(422, "Promotion blocked by failed gates", f"Failed gates: {', '.join(failed_names)}")

    await _set_env_pointer(
        session, bot_id=bot_id, environment=target_env, bundle_id=bundle_id,
        allow_production_data=allow_production_data,
    )
    if target_env == "prod":
        bot.production_bundle_id = bundle_id

    details: dict = {"source": source_env, "target": target_env}
    if gate_result is not None:
        details["gates_passed"] = True
        details["gate_count"] = len(gate_result["gates"])
    await audit.record(session, f"user:{actor.id}", "bot.env.promote", f"bot:{bot_id}", details)
    await session.commit()
    return await session.get(BotBundle, bundle_id)


async def grant_bot_access(
    session: AsyncSession, *, actor: User, bot_id: uuid.UUID, principal: str, level: str = "user"
) -> BotGrant:
    await _load_bot(session, bot_id)
    grant = BotGrant(bot_id=bot_id, principal=principal, level=level)
    await session.merge(grant)
    await audit.record(session, f"user:{actor.id}", "bot.access.grant", f"bot:{bot_id}", {"principal": principal})
    await session.commit()
    return grant


async def set_bot_scope(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID] = (),
    folder_ids: Sequence[uuid.UUID] = (),
) -> None:
    await _load_bot(session, bot_id)
    await session.execute(delete(BotScope).where(BotScope.bot_id == bot_id))
    for document_id in document_ids:
        session.add(BotScope(bot_id=bot_id, target_type="document", target_id=document_id))
    for folder_id in folder_ids:
        session.add(BotScope(bot_id=bot_id, target_type="folder", target_id=folder_id))
    await audit.record(
        session,
        f"user:{actor.id}",
        "bot.scope.set",
        f"bot:{bot_id}",
        {"documents": len(document_ids), "folders": len(folder_ids)},
    )
    await session.commit()


async def answer_bot_question(
    session: AsyncSession,
    *,
    embedder: Embedder,
    user: User,
    bot_id: uuid.UUID,
    question: str,
    include_explainability: bool = False,
) -> dict:
    bot = await session.get(Bot, bot_id)
    if bot is None or bot.production_bundle_id is None:
        return {"answer": "I don't have access to that bot.", "citations": []}
    user_principals = await principals(session, user)
    allowed = await _user_has_bot_access(session, bot_id=bot_id, user_principals=user_principals)
    if not allowed:
        await audit.record(session, f"user:{user.id}", "bot.access.denied", f"bot:{bot_id}", {})
        await session.commit()
        return {"answer": "I don't have access to that bot.", "citations": []}
    scopes = list((await session.execute(select(BotScope).where(BotScope.bot_id == bot_id))).scalars().all())
    scoped_document_ids = [s.target_id for s in scopes if s.target_type == "document"]
    scoped_folder_ids = [s.target_id for s in scopes if s.target_type == "folder"]
    return await answer_question(
        session,
        embedder=embedder,
        user=user,
        question=question,
        scoped_document_ids=scoped_document_ids,
        scoped_folder_ids=scoped_folder_ids,
        include_explainability=include_explainability,
    )


async def _user_has_bot_access(session: AsyncSession, *, bot_id: uuid.UUID, user_principals: set[str]) -> bool:
    if not user_principals:
        return False
    return (await session.scalar(
        select(func.count()).select_from(BotGrant).where(BotGrant.bot_id == bot_id, BotGrant.principal.in_(sorted(user_principals)))
    )) > 0


async def _load_bot(session: AsyncSession, bot_id: uuid.UUID) -> Bot:
    bot = await session.get(Bot, bot_id)
    if bot is None:
        raise AppError(404, "Bot not found")
    return bot


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class BotIn(BaseModel):
    name: str


class ReleaseGatePolicyIn(BaseModel):
    eval_threshold: float | None = None
    eval_adapter: str = "ragas.local"
    eval_metric: str = "answer_correctness"
    require_zero_leaks: bool = False
    redteam_pass_rate: float | None = None
    require_human_signoff: bool = False

    def to_policy(self) -> ReleaseGatePolicy:
        return ReleaseGatePolicy(
            eval_threshold=self.eval_threshold,
            eval_adapter=self.eval_adapter,
            eval_metric=self.eval_metric,
            require_zero_leaks=self.require_zero_leaks,
            redteam_pass_rate=self.redteam_pass_rate,
            require_human_signoff=self.require_human_signoff,
        )


class BundleIn(BaseModel):
    bundle: dict
    release_gates: ReleaseGatePolicyIn | None = None
    human_signoff: bool = False


class EnvironmentReleaseIn(BaseModel):
    bundle: dict
    environment: str = "dev"


class PromoteIn(BaseModel):
    source_env: str
    target_env: str
    release_gates: ReleaseGatePolicyIn | None = None
    human_signoff: bool = False
    allow_production_data: bool = False


class GrantIn(BaseModel):
    principal: str
    level: str = "user"


class ScopeIn(BaseModel):
    document_ids: list[uuid.UUID] = []
    folder_ids: list[uuid.UUID] = []


class BotAskIn(BaseModel):
    question: str
    include_explainability: bool = False


router = APIRouter(prefix="/api/v1/bots", tags=["bots"])


@router.post("")
async def create_bot_api(body: BotIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bot = await create_bot(db, owner=user, name=body.name)
    return {"id": str(bot.id), "name": bot.name}


@router.post("/{bot_id}/bundles")
async def release_bundle_api(bot_id: uuid.UUID, body: BundleIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await release_bundle(
        db,
        actor=user,
        bot_id=bot_id,
        bundle=body.bundle,
        gate_policy=body.release_gates.to_policy() if body.release_gates else None,
        gate_human_signoff=body.human_signoff,
    )
    return {"id": str(bundle.id), "version": bundle.version, "status": bundle.status}


@router.post("/{bot_id}/environments/release")
async def release_to_environment_api(bot_id: uuid.UUID, body: EnvironmentReleaseIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await release_to_environment(db, actor=user, bot_id=bot_id, bundle=body.bundle, environment=body.environment)
    return {"id": str(bundle.id), "version": bundle.version, "environment": body.environment}


@router.post("/{bot_id}/environments/promote")
async def promote_bundle_api(bot_id: uuid.UUID, body: PromoteIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await promote_bundle(
        db, actor=user, bot_id=bot_id,
        source_env=body.source_env, target_env=body.target_env,
        gate_policy=body.release_gates.to_policy() if body.release_gates else None,
        gate_human_signoff=body.human_signoff,
        allow_production_data=body.allow_production_data,
    )
    return {"id": str(bundle.id), "version": bundle.version, "source_env": body.source_env, "target_env": body.target_env}


@router.post("/{bot_id}/bundles/{bundle_id}/rollback")
async def rollback_bundle_api(bot_id: uuid.UUID, bundle_id: uuid.UUID, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await rollback_bundle(db, actor=user, bot_id=bot_id, target_bundle_id=bundle_id)
    return {"id": str(bundle.id), "version": bundle.version, "status": bundle.status}


@router.post("/{bot_id}/grants")
async def grant_bot_api(bot_id: uuid.UUID, body: GrantIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    grant = await grant_bot_access(db, actor=user, bot_id=bot_id, principal=body.principal, level=body.level)
    return {"principal": grant.principal, "level": grant.level}


@router.put("/{bot_id}/scope")
async def set_bot_scope_api(bot_id: uuid.UUID, body: ScopeIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    await set_bot_scope(db, actor=user, bot_id=bot_id, document_ids=body.document_ids, folder_ids=body.folder_ids)
    return {"status": "ok", "documents": len(body.document_ids), "folders": len(body.folder_ids)}


@router.post("/{bot_id}/ask")
async def ask_bot_api(bot_id: uuid.UUID, body: BotAskIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    from .auth import redis_client
    from .quotas import enforce_request_quota, enforce_token_quota, estimate_tokens, get_effective_policy, record_token_usage

    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    if not body.question.strip():
        raise AppError(400, "Question is required")

    # FR-F13: enforce request + token quotas
    redis = redis_client()
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis, user_id=sess["user_id"], endpoint="bot_ask", policy=policy)
    await enforce_token_quota(redis, user_id=sess["user_id"], estimated_tokens=estimate_tokens(body.question), policy=policy)

    result = await answer_bot_question(db, embedder=LiteLLMEmbedder.from_settings(), user=user, bot_id=bot_id, question=body.question, include_explainability=body.include_explainability)

    # Record token usage (best-effort)
    answer_tokens = estimate_tokens(result.get("answer", ""))
    await record_token_usage(redis, user_id=sess["user_id"], tokens=estimate_tokens(body.question) + answer_tokens)

    return result
