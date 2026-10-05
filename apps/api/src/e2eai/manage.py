"""Developer/operator commands for the API app."""

import asyncio
import subprocess
import uuid
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, help=__doc__)


def _run(coro):
    from .db import sessions

    async def _with_session():
        async with sessions()() as session:
            return await coro(session)

    return asyncio.run(_with_session())


@app.command()
def migrate() -> None:
    """Apply database migrations (FR-F16)."""
    subprocess.run(["alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[2], check=True)


@app.command("check-config")
def check_config() -> None:
    """Load settings and fail fast with a clear error when config is invalid (FR-F21)."""
    from .core.config import get_settings

    s = get_settings()
    typer.echo(f"tier={s.tier} database=configured openfga={s.openfga_url} litellm={s.litellm_url}")


@app.command("bootstrap-admin")
def bootstrap_admin_cmd() -> None:
    """Create the break-glass admin and print its password once (FR-F2a). Never stored in plaintext."""
    from .seed import ADMIN_EMAIL, bootstrap_admin

    password = _run(bootstrap_admin)
    if password is None:
        typer.echo(f"{ADMIN_EMAIL} already exists; password unchanged.")
        return
    typer.secho(f"Bootstrap admin created: {ADMIN_EMAIL}", fg=typer.colors.GREEN)
    typer.secho(f"Password (shown once — store it now): {password}", fg=typer.colors.YELLOW)


@app.command("seed-demo")
def seed_demo_cmd() -> None:
    """Seed the demo org (Org 'Demo'; Sales/HR; Andi, Budi, intern) and print the shared password once."""
    from .seed import seed_demo

    password = _run(seed_demo)
    if password is None:
        typer.echo("Demo org already present; nothing to do.")
        return
    typer.secho("Demo org seeded (Andi, Budi, Intern).", fg=typer.colors.GREEN)
    typer.secho(f"Demo user password (shown once): {password}", fg=typer.colors.YELLOW)


@app.command("bootstrap-authz")
def bootstrap_authz_cmd() -> None:
    """Create/find the OpenFGA store and write the PRD T4 model if it changed (PRD T4). Idempotent."""
    from .authz import connect
    from .core.config import get_settings

    authz = _run(lambda session: connect(get_settings(), session))
    typer.secho("OpenFGA ready.", fg=typer.colors.GREEN)
    typer.echo(f"store_id={authz.store_id} model_id={authz.model_id}")


@app.command("verify-phase-0")
def verify_phase0_cmd() -> None:
    """Exercise the whole Phase 0 slice against the running stack; exit non-zero on any failure."""
    from .verify import run

    raise typer.Exit(run())


@app.command("index-document")
def index_document_cmd(document_id: str) -> None:
    """Embed and index current chunks for one document through LiteLLM (Phase 1 FR-C1)."""
    from .retrieval import LiteLLMEmbedder, index_document_chunks

    doc_id = uuid.UUID(document_id)
    count = _run(lambda session: index_document_chunks(session, embedder=LiteLLMEmbedder.from_settings(), document_id=doc_id))
    typer.secho(f"Indexed {count} chunk(s) for document {doc_id}", fg=typer.colors.GREEN)


def _actor(session, actor_email: str):
    from sqlalchemy import func, select
    from .db import User

    return session.scalar(select(User).where(func.lower(User.email) == actor_email.lower()))


@app.command("trash-document")
def trash_document_cmd(document_id: str, actor_email: str) -> None:
    """Move a document to trash as the given owner (FR-D9)."""
    from .documents import trash_document

    doc_id = uuid.UUID(document_id)

    async def _do(session):
        await trash_document(session, actor=await _actor(session, actor_email), document_id=doc_id)

    _run(_do)
    typer.secho(f"Trashed document {doc_id}", fg=typer.colors.GREEN)


@app.command("restore-document")
def restore_document_cmd(document_id: str, actor_email: str) -> None:
    """Restore a document from trash within the retention window (FR-D9)."""
    from .documents import restore_document

    doc_id = uuid.UUID(document_id)

    async def _do(session):
        await restore_document(session, actor=await _actor(session, actor_email), document_id=doc_id)

    _run(_do)
    typer.secho(f"Restored document {doc_id}", fg=typer.colors.GREEN)


@app.command("purge-document")
def purge_document_cmd(document_id: str, actor_email: str) -> None:
    """Permanently purge a document; blocked under legal hold (FR-D9, FR-D13)."""
    from .authz import connect
    from .core.config import get_settings
    from .documents import purge_document

    doc_id = uuid.UUID(document_id)

    async def _do(session):
        authz = await connect(get_settings(), session)
        await purge_document(session, authz, actor=await _actor(session, actor_email), document_id=doc_id)

    _run(_do)
    typer.secho(f"Purged document {doc_id}", fg=typer.colors.GREEN)


@app.command("ingest-version")
def ingest_version_cmd(version_id: str) -> None:
    """Parse a stored document version, chunk, and index it through LiteLLM (Phase 1 FR-D1/FR-D3)."""
    from .ingest import ingest_version
    from .retrieval import LiteLLMEmbedder

    vid = uuid.UUID(version_id)
    result = _run(lambda session: ingest_version(session, embedder=LiteLLMEmbedder.from_settings(), version_id=vid))
    color = typer.colors.GREEN if result["status"] == "ready" else typer.colors.RED
    typer.secho(f"ingest {vid}: {result}", fg=color)
