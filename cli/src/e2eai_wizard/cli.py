"""`e2eai` install wizard: services, ports, usernames and passwords -> Docker Compose config."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import detect, generate
from .services import BY_NAME, SECRETS, SERVICES, USERS, enabled_services, owner_enabled

app = typer.Typer(add_completion=False, help=__doc__)
out = Console()


def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "deploy" / "versions.lock").exists():
            return p
    raise typer.BadParameter("run inside the E2EAIDEV repo (deploy/versions.lock not found)")


def _ask_port(label: str, default: int, taken: set[int]) -> int:
    while True:
        port = typer.prompt(f"  Port for {label}", default=default, type=int)
        if not 1024 <= port <= 65535:
            out.print("  [red]Use a port between 1024 and 65535.[/red]")
        elif port in taken:
            out.print("  [red]Already used by another service in this install.[/red]")
        elif port != default and detect.port_in_use(port):
            out.print(f"  [red]Port {port} is in use on this machine.[/red]")
        else:
            return port


def _ask_user(label: str, default: str) -> str:
    while True:
        value = typer.prompt(f"  {label}", default=default)
        if (err := generate.validate_username(value)) is None:
            return value
        out.print(f"  [red]{err}[/red]")


def _ask_secret(label: str, prefix: str) -> str:
    while True:
        value = typer.prompt(f"  {label} [dim](Enter = generate)[/dim]", default="", hide_input=True, show_default=False)
        if not value:
            return generate.new_secret(prefix)
        err = generate.validate_secret(value)
        if err is None and prefix and not value.startswith(prefix):
            err = f"must start with '{prefix}'"
        if err is None:
            return value
        out.print(f"  [red]{err}[/red]")


@app.command()
def main(
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept every recommended default (non-interactive)."),
    root: Path | None = typer.Option(None, help="Repo root (default: auto-detect)."),
    force: bool = typer.Option(False, help="Overwrite an existing deploy/compose/.env (a backup is kept)."),
) -> None:
    root = root or _find_root(Path.cwd())

    # 1. Detect -------------------------------------------------------------
    hw = detect.hardware(root)
    docker = detect.docker_version()
    host_ollama = detect.host_ollama_version()
    out.print("\n[bold]1/5 This machine[/bold]")
    out.print(f"  CPU {hw.cpus} threads · RAM {hw.ram_gb} GB · free disk {hw.disk_free_gb} GB")
    out.print(f"  GPU: {f'{hw.gpu.name} ({hw.gpu.vram_gb} GB)' if hw.gpu else 'none detected'}")
    out.print(f"  Docker: {docker or '[red]not running[/red] (config is still written; start Docker before `up`)'}")
    out.print(f"  Ollama on this PC: {host_ollama or 'not found'}")
    if hw.disk_free_gb < 50:
        out.print("  [yellow]Less than 50 GB free; models and documents may not fit (PRD §12).[/yellow]")

    # 2. Tier and network -----------------------------------------------------
    tier = detect.recommend_tier(hw.ram_gb)
    out.print(f"\n[bold]2/5 Tier[/bold]  recommended: [green]{tier}[/green] (PRD §12)")
    if not yes:
        tier = typer.prompt("  Tier", default=tier, type=typer.Choice(["lite", "standard"]))
    use_host_ollama = bool(host_ollama) and (yes or typer.confirm(f"  Use the Ollama already running on this PC (v{host_ollama})?", default=True))
    gpu = bool(hw.gpu) and not use_host_ollama and (yes or typer.confirm("  Use the NVIDIA GPU for the Ollama container?", default=True))
    a = generate.default_answers(tier=tier, ports={}, host_ollama=use_host_ollama, gpu=gpu)
    if not yes and typer.confirm("  Expose services on ALL network interfaces (0.0.0.0)? Not recommended", default=False):
        a["bind"] = "0.0.0.0"

    # 3. Services ---------------------------------------------------------------
    out.print("\n[bold]3/5 Services[/bold]  always installed: " + ", ".join(s.name for s in SERVICES if s.profile is None))
    if not yes:
        if not use_host_ollama:
            a["optional"]["ollama"] = typer.confirm("  Run Ollama in Docker?", default=True)
        a["optional"]["keycloak"] = typer.confirm("  Keycloak SSO (heavier; usually Standard tier)?", default=a["optional"]["keycloak"])
        for name, what in (("tei-embed", "embedding"), ("tei-rerank", "reranker")):
            model = typer.prompt(f"  Hugging Face {what} model id for TEI (blank = skip for now)", default="", show_default=False)
            a["tei_models"][name] = model.strip()
            a["optional"][name] = bool(model.strip())
    enabled = enabled_services(a)

    # 4. Ports ------------------------------------------------------------------
    out.print("\n[bold]4/5 Ports[/bold]  (bound to " + a["bind"] + "; busy ports are skipped automatically)")
    taken: set[int] = set()
    for name in enabled:
        s = BY_NAME[name]
        suggested = detect.suggest_port(s.default_port, taken)
        port = suggested if yes else _ask_port(s.label, suggested, taken)
        if yes and suggested != s.default_port:
            out.print(f"  {s.label}: {s.default_port} busy -> {suggested}")
        a["ports"][name] = port
        taken.add(port)

    # 5. Credentials --------------------------------------------------------------
    out.print("\n[bold]5/5 Usernames and passwords[/bold]")
    if not yes:
        for key, (owner, label, _) in USERS.items():
            if owner_enabled(owner, enabled):
                a["users"][key] = _ask_user(label, a["users"][key])
        for key, (owner, label, prefix) in SECRETS.items():
            if owner_enabled(owner, enabled):
                a["secrets"][key] = _ask_secret(label, prefix)
    else:
        out.print("  All passwords generated (32+ random characters).")

    # Write ------------------------------------------------------------------
    if detect.docker_volume_exists("e2eai_pgdata"):
        out.print("[yellow]Existing database volume e2eai_pgdata found: new database passwords only apply to a fresh volume.[/yellow]")
    try:
        written = generate.write_all(root, a, force=force)
    except FileExistsError as e:
        if yes or not typer.confirm(f"\n{e} exists. Replace it (a backup is kept)?", default=False):
            out.print("[red]Nothing written.[/red] Re-run with --force to replace the existing config.")
            raise typer.Exit(1)
        written = generate.write_all(root, a, force=True)

    table = Table("Service", "URL", "Username", "Password / key")
    for name in enabled:
        users = [k for k, (o, _, _) in USERS.items() if o == name]
        keys = [k for k, (o, _, _) in SECRETS.items() if o == name or (o == "tei" and name.startswith("tei"))]
        table.add_row(BY_NAME[name].label, f"http://{a['bind'] if a['bind'] != '0.0.0.0' else '127.0.0.1'}:{a['ports'][name]}",
                      ", ".join(a["users"][u] for u in users) or "-", ", ".join(f".env: {k}" for k in keys) or "-")
    out.print()
    out.print(table)
    out.print("Written: " + ", ".join(str(p.relative_to(root)) for p in written))
    out.print("\n[bold]Next:[/bold]  cd deploy/compose && docker compose up -d && docker compose ps")
