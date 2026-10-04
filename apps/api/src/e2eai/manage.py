"""Developer/operator commands for the API app."""

import subprocess
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, help=__doc__)


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
