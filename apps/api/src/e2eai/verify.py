"""verify-phase-0: one command that exercises the whole Phase 0 slice against the running stack.

Run: cd apps/api && uv run e2eai-api verify-phase-0
Each step is reported pass/fail; the command exits non-zero if any step fails. It needs the
compose stack up (cd deploy/compose && docker compose up -d) and the wizard-generated .env."""

import asyncio
import subprocess

import httpx
import yaml

from .core.config import get_settings, repo_root


def _compose_ps() -> tuple[bool, str]:
    root = repo_root()
    r = subprocess.run(["docker", "compose", "ps"], cwd=root / "deploy" / "compose",
                       capture_output=True, text=True)
    running = sum(1 for ln in r.stdout.splitlines()[1:] if ln.strip())
    return r.returncode == 0 and running > 0, f"{running} service(s) listed"


def _pytest(subdir: str) -> tuple[bool, str]:
    r = subprocess.run(["uv", "run", "pytest", "-q"], cwd=repo_root() / subdir,
                       capture_output=True, text=True)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return r.returncode == 0, tail


def _alembic_upgrade() -> tuple[bool, str]:
    r = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=repo_root() / "apps" / "api",
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "ok"


def _api_health_ready() -> tuple[bool, str]:
    from fastapi.testclient import TestClient

    from .main import create_app

    with TestClient(create_app()) as c:
        h = c.get("/api/v1/health")
        rd = c.get("/api/v1/ready")
    ok = h.status_code == 200 and rd.status_code == 200
    return ok, f"health={h.status_code} ready={rd.status_code}"


def _models() -> dict:
    return yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8")).get("models", {})


def _litellm_chat() -> tuple[bool, str]:
    s = get_settings()
    chat = (_models().get("chat") or [None])[0]
    if not chat:
        return False, "no chat model configured in e2eai.yaml"
    r = httpx.post(f"{s.litellm_url}/v1/chat/completions", timeout=120,
                   headers={"Authorization": f"Bearer {s.litellm_key}"},
                   json={"model": chat, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8})
    ok = r.status_code == 200 and bool(r.json().get("choices"))
    return ok, f"{chat}: {r.status_code}"


def _litellm_embedding() -> tuple[bool, str]:
    s = get_settings()
    embed = (_models().get("embedding") or [None])[0]
    if not embed:
        return False, "no embedding model configured in e2eai.yaml"
    r = httpx.post(f"{s.litellm_url}/v1/embeddings", timeout=120,
                   headers={"Authorization": f"Bearer {s.litellm_key}"},
                   json={"model": embed, "input": "ping"})
    dim = len((r.json().get("data") or [{}])[0].get("embedding", [])) if r.status_code == 200 else 0
    return r.status_code == 200 and dim > 0, f"{embed}: {r.status_code}, dim={dim}"


def _openfga_model_and_check() -> tuple[bool, str]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from .authz import connect

    async def run():
        # A throwaway engine, created and disposed inside this loop: the cached engine from db.py
        # may have opened asyncpg connections on an earlier step's (now-closed) event loop.
        eng = create_async_engine(get_settings().database_url)
        try:
            async with async_sessionmaker(eng)() as session:
                authz = await connect(get_settings(), session)
            # Model is written; an unshared document must deny (fail closed, NFR-19).
            denied = await authz.check("user:nobody", "viewer", "document:does-not-exist") is False
            return authz.model_id, denied
        finally:
            await eng.dispose()

    model_id, denied = asyncio.run(run())
    return bool(model_id) and denied, f"model={model_id[:12]}… deny-unshared={denied}"


STEPS = [
    ("compose health", _compose_ps),
    ("cli tests", lambda: _pytest("cli")),
    ("api tests", lambda: _pytest("apps/api")),
    ("alembic upgrade", _alembic_upgrade),
    ("api health/ready", _api_health_ready),
    ("litellm chat", _litellm_chat),
    ("litellm embedding", _litellm_embedding),
    ("openfga model + fail-closed", _openfga_model_and_check),
]


def run() -> int:
    """Run every step, print results, return a process exit code."""
    failures = 0
    for name, fn in STEPS:
        try:
            ok, detail = fn()
        except Exception as e:  # a step that raises is a failure, not a crash
            ok, detail = False, f"{type(e).__name__}: {e}"
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\n{'ALL PASSED' if not failures else f'{failures} STEP(S) FAILED'}")
    return 1 if failures else 0
