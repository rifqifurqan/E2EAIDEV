"""Developer/operator commands for the API app."""

import asyncio
import subprocess
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
