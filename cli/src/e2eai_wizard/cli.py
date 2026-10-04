"""`e2eai` install wizard: services, ports, usernames/passwords, and models -> Docker Compose config."""

import json
import urllib.request
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import detect, generate, models
from .services import BY_NAME, SECRETS, SERVICES, USERS, enabled_services, owner_enabled

app = typer.Typer(add_completion=False, help=__doc__, no_args_is_help=True)
out = Console()
ROLE_LABELS = {
    "chat": "Chat model (pick one or more, comma-separated)",
    "embedding": "Embedding model (pick one)",
    "reranker": "Reranker (pick one, 0 = none)",
    "vision": "Vision model for figures and scans, optional (FR-D15)",
    "safety": "Safety classifier, optional (FR-O9)",
}


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


def _machine(a: dict, hw: detect.Hardware) -> models.Machine:
    # Host Ollama uses the host GPU directly; the Ollama container only when the GPU override is on.
    gpu = hw.gpu.vram_gb if hw.gpu and (a["host_ollama"] or a["gpu"]) else 0.0
    return models.Machine(ram_gb=hw.ram_gb, gpu_vram_gb=gpu, docker_mem_gb=detect.docker_mem_gb() or 0.0)


def _choose_role(role: str, catalog: dict, machine: models.Machine, recommended: list[str], tei_used: float) -> list[str]:
    options = [m for m in catalog.values() if m.role == role]
    table = Table("#", "Model", "Served by", "Download", "Runs on", "License", "", title=ROLE_LABELS[role])
    fits = {}
    for i, m in enumerate(options, 1):
        fits[i] = models.fit(m, machine, tei_used if m.served_by == "tei" else 0.0)
        runs = {"gpu": "[green]GPU[/green]", "cpu": "CPU (slower)" if m.served_by == "ollama" else "Docker CPU",
                "too_big": "[red]too big[/red]"}[fits[i]]
        lic = m.license if m.license_class == "permissive" else f"[yellow]{m.license}[/yellow]"
        table.add_row(str(i), m.id, m.served_by, f"{m.size_gb} GB", runs, lic, "* recommended" if m.id in recommended else "")
    out.print(table)
    default = ",".join(str(i) for i, m in enumerate(options, 1) if m.id in recommended) or "0"
    while True:
        raw = typer.prompt("  Choice (0 = none)", default=default)
        try:
            picks = sorted({int(x) for x in raw.split(",") if x.strip()} - {0})
        except ValueError:
            out.print("  [red]Enter numbers from the table, e.g. 2 or 1,3[/red]")
            continue
        if len(picks) > 1 and role not in models.MULTI:
            out.print("  [red]Pick only one for this role.[/red]")
        elif any(p not in fits for p in picks):
            out.print("  [red]Number not in the table.[/red]")
        elif any(fits[p] == "too_big" for p in picks):
            out.print("  [red]That model doesn't fit this machine (FR-F5b). Pick a smaller one.[/red]")
        else:
            chosen = [options[p - 1] for p in picks]
            warnings = [w for m in chosen if (w := models.license_warning(m))]
            for w in warnings:
                out.print(f"  [yellow]{w}[/yellow]")
            if any("NON-COMMERCIAL" in w for w in warnings) and not typer.confirm("  Use it anyway?", default=False):
                continue
            return [m.id for m in chosen]


def _model_step(a: dict, hw: detect.Hardware, root: Path, yes: bool) -> None:
    catalog = models.load_catalog(root)
    machine = _machine(a, hw)
    rec = models.recommend_all(catalog, machine)
    out.print(f"\n[bold]Models[/bold]  GPU for Ollama: {machine.gpu_vram_gb} GB | Docker memory: {machine.docker_mem_gb} GB "
              "(no model is pre-installed; * = recommended for this machine)")
    if yes:
        selection = rec | {"external": []}
    else:
        selection = {"external": []}
        for role in models.ROLES:
            used = sum(catalog[i].mem_gb for i in selection.get("embedding", []) if catalog[i].served_by == "tei")
            selection[role] = _choose_role(role, catalog, machine, rec[role], used)
        if typer.confirm("  Add external API models (OpenAI / Anthropic / Gemini)? Data will leave this machine (FR-M9)", default=False):
            while True:
                provider = typer.prompt("  Provider", type=typer.Choice(list(models.EXTERNAL_PROVIDERS)))
                model = typer.prompt("  Model name as the provider spells it (e.g. gpt-5-mini)").strip()
                key_env = models.EXTERNAL_PROVIDERS[provider][1]
                if key_env not in a["api_keys"]:
                    a["api_keys"][key_env] = typer.prompt(f"  {key_env}", hide_input=True).strip()
                selection["external"].append({"provider": provider, "model": model})
                if not typer.confirm("  Add another external model?", default=False):
                    break
    if not selection["chat"] and not selection["external"]:
        out.print("  [yellow]No chat model chosen: the chatbot can't answer until you run `uv run e2eai models`.[/yellow]")
    models.apply_selection(a, selection, catalog)


def _pull(a: dict, root: Path, yes: bool) -> None:
    catalog = models.load_catalog(root)
    tags = [catalog[i].source for r in models.ROLES for i in a["models"][r] if catalog[i].served_by == "ollama"]
    if not tags:
        return
    if not a["host_ollama"]:
        out.print("\nAfter `docker compose up -d`, download the models with:")
        for t in tags:
            out.print(f"  docker compose exec ollama ollama pull {t}")
        return
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
            have = {m["name"] for m in json.load(r)["models"]}
    except OSError:
        out.print("[yellow]Host Ollama not reachable; pull the models later with `ollama pull <name>`.[/yellow]")
        return
    missing = [t for t in tags if t not in have and f"{t}:latest" not in have]
    if not missing or not (yes or typer.confirm(f"\nDownload {', '.join(missing)} into the Ollama on this PC now?", default=True)):
        return
    for tag in missing:
        out.print(f"  pulling {tag} ...")
        req = urllib.request.Request("http://127.0.0.1:11434/api/pull", data=json.dumps({"model": tag}).encode())
        with urllib.request.urlopen(req, timeout=3600) as r:
            last = -10
            for line in r:
                ev = json.loads(line)
                if ev.get("error"):
                    out.print(f"[red]{ev['error'].strip()}[/red]")
                    if "newer version" in ev["error"]:
                        out.print("  Update the Ollama on this PC, or re-run `uv run e2eai init --force` and answer "
                                  "'no' to using it: the pinned Ollama container is newer.")
                    raise typer.Exit(1)
                if ev.get("total"):
                    pct = int(ev.get("completed", 0) * 100 / ev["total"])
                    if pct >= last + 10:
                        out.print(f"    {pct}%")
                        last = pct
        out.print(f"  [green]{tag} ready[/green]")


def _write(root: Path, a: dict, yes: bool, force: bool) -> list[Path]:
    try:
        return generate.write_all(root, a, force=force)
    except FileExistsError as e:
        if yes or not typer.confirm(f"\n{e} exists. Replace it (a backup is kept)?", default=False):
            out.print("[red]Nothing written.[/red] Re-run with --force to replace the existing config.")
            raise typer.Exit(1)
        return generate.write_all(root, a, force=True)


def _summary(root: Path, a: dict, written: list[Path]) -> None:
    table = Table("Service", "URL", "Username", "Password / key")
    host = a["bind"] if a["bind"] != "0.0.0.0" else "127.0.0.1"
    for name in enabled_services(a):
        users = [k for k, (o, _, _) in USERS.items() if o == name]
        keys = [k for k, (o, _, _) in SECRETS.items() if o == name or (o == "tei" and name.startswith("tei"))]
        table.add_row(BY_NAME[name].label, f"http://{host}:{a['ports'][name]}",
                      ", ".join(a["users"][u] for u in users) or "-", ", ".join(f".env: {k}" for k in keys) or "-")
    out.print()
    out.print(table)
    picked = {r: v for r, v in a["models"].items() if v}
    out.print("Models: " + (", ".join(f"{r}={v}" for r, v in picked.items()) or "none"))
    out.print("Written: " + ", ".join(str(p.relative_to(root)) for p in written))


@app.command()
def init(
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept every recommendation (non-interactive)."),
    root: Path | None = typer.Option(None, help="Repo root (default: auto-detect)."),
    force: bool = typer.Option(False, help="Overwrite an existing deploy/compose/.env (a backup is kept)."),
    pull: bool = typer.Option(True, help="Download chosen Ollama models now."),
) -> None:
    """Full setup: machine check, tier, services, models, ports, usernames and passwords."""
    root = root or _find_root(Path.cwd())

    hw = detect.hardware(root)
    docker = detect.docker_version()
    host_ollama = detect.host_ollama_version()
    out.print("\n[bold]1/6 This machine[/bold]")
    out.print(f"  CPU {hw.cpus} threads | RAM {hw.ram_gb} GB | free disk {hw.disk_free_gb} GB | Docker memory {detect.docker_mem_gb() or '?'} GB")
    out.print(f"  GPU: {f'{hw.gpu.name} ({hw.gpu.vram_gb} GB)' if hw.gpu else 'none detected'}")
    out.print(f"  Docker: {docker or '[red]not running[/red] (config is still written; start Docker before `up`)'}")
    out.print(f"  Ollama on this PC: {host_ollama or 'not found'}")
    if hw.disk_free_gb < 50:
        out.print("  [yellow]Less than 50 GB free; models and documents may not fit (PRD section 12).[/yellow]")

    tier = detect.recommend_tier(hw.ram_gb)
    out.print(f"\n[bold]2/6 Tier[/bold]  recommended: [green]{tier}[/green] (PRD section 12)")
    if not yes:
        tier = typer.prompt("  Tier", default=tier, type=typer.Choice(["lite", "standard"]))
    host_ok = bool(host_ollama) and detect.version_at_least(host_ollama, detect.pinned_ollama_version(root))
    if host_ollama and not host_ok:
        out.print(f"  [yellow]Ollama on this PC (v{host_ollama}) is older than the pinned container "
                  f"(v{detect.pinned_ollama_version(root)}); newer models may not run on it.[/yellow]")
    use_host = bool(host_ollama) and (
        host_ok if yes else typer.confirm(f"  Use the Ollama already running on this PC (v{host_ollama})?", default=host_ok))
    gpu = bool(hw.gpu) and not use_host and (yes or typer.confirm("  Use the NVIDIA GPU for the Ollama container?", default=True))
    a = generate.default_answers(tier=tier, ports={}, host_ollama=use_host, gpu=gpu)
    if not yes and typer.confirm("  Expose services on ALL network interfaces (0.0.0.0)? Not recommended", default=False):
        a["bind"] = "0.0.0.0"

    out.print("\n[bold]3/6 Services[/bold]  always installed: " + ", ".join(s.name for s in SERVICES if s.profile is None))
    if not yes:
        a["optional"]["keycloak"] = typer.confirm("  Keycloak SSO (heavier; usually Standard tier)?", default=a["optional"]["keycloak"])

    out.print("\n[bold]4/6[/bold]", end="")
    _model_step(a, hw, root, yes)

    out.print("\n[bold]5/6 Ports[/bold]  (bound to " + a["bind"] + "; busy ports are skipped automatically)")
    taken: set[int] = set()
    for name in enabled_services(a):
        s = BY_NAME[name]
        suggested = detect.suggest_port(s.default_port, taken)
        port = suggested if yes else _ask_port(s.label, suggested, taken)
        if yes and suggested != s.default_port:
            out.print(f"  {s.label}: {s.default_port} busy -> {suggested}")
        a["ports"][name] = port
        taken.add(port)

    out.print("\n[bold]6/6 Usernames and passwords[/bold]")
    enabled = enabled_services(a)
    if yes:
        out.print("  All passwords generated (32+ random characters).")
    else:
        for key, (owner, label, _) in USERS.items():
            if owner_enabled(owner, enabled):
                a["users"][key] = _ask_user(label, a["users"][key])
        for key, (owner, label, prefix) in SECRETS.items():
            if owner_enabled(owner, enabled):
                a["secrets"][key] = _ask_secret(label, prefix)

    if detect.docker_volume_exists("e2eai_pgdata"):
        out.print("[yellow]Existing database volume e2eai_pgdata: new database passwords only apply to a fresh volume. "
                  "To change only models, use `uv run e2eai models`.[/yellow]")
    written = _write(root, a, yes, force)
    _summary(root, a, written)
    if pull:
        _pull(a, root, yes)
    out.print("\n[bold]Next:[/bold]  cd deploy/compose && docker compose up -d && docker compose ps")


@app.command("models")
def models_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept the hardware recommendation."),
    root: Path | None = typer.Option(None, help="Repo root (default: auto-detect)."),
    pull: bool = typer.Option(True, help="Download chosen Ollama models now."),
) -> None:
    """Change models on an existing install. Passwords and ports stay the same."""
    root = root or _find_root(Path.cwd())
    try:
        a = generate.load_answers(root)
    except FileNotFoundError:
        out.print("[red]No install found. Run `uv run e2eai init` first.[/red]")
        raise typer.Exit(1)
    hw = detect.hardware(root)
    _model_step(a, hw, root, yes)
    taken = set(a["ports"].values())
    for name in enabled_services(a):  # a newly enabled TEI/Ollama service may need a port
        if detect.port_in_use(a["ports"][name]) and name in ("tei-embed", "tei-rerank", "ollama"):
            a["ports"][name] = detect.suggest_port(BY_NAME[name].default_port, taken)
            taken.add(a["ports"][name])
    written = generate.write_all(root, a, force=True)
    _summary(root, a, written)
    if pull:
        _pull(a, root, yes)
    out.print("\n[bold]Apply:[/bold]  cd deploy/compose && docker compose up -d   (restarts LiteLLM and starts TEI if needed)")
