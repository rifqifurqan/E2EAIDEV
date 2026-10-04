"""Settings from e2eai.yaml + deploy/compose/.env (FR-F21). In development the API runs on the host,
so services are reached on 127.0.0.1 at the ports the wizard chose. Real environment variables win."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


def repo_root() -> Path:
    if env := os.environ.get("E2EAI_ROOT"):
        return Path(env)
    for p in Path(__file__).resolve().parents:
        if (p / "deploy" / "versions.lock").exists():
            return p
    raise RuntimeError("repo root not found; set E2EAI_ROOT")


def _env(root: Path) -> dict[str, str]:
    path = root / "deploy" / "compose" / ".env"
    if not path.exists():
        raise RuntimeError(f"{path} missing: run the wizard first (cd cli && uv run e2eai init)")
    lines = path.read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    return values | {k: v for k, v in os.environ.items() if k in values or k.startswith("E2EAI_")}


@dataclass(frozen=True)
class Settings:
    tier: str
    database_url: str
    valkey_url: str
    openfga_url: str
    openfga_key: str
    openfga_store: str
    litellm_url: str
    litellm_key: str
    s3_url: str
    s3_access_key: str
    s3_secret_key: str
    default_language: str
    time_zone: str
    session_idle_hours: int = 8  # NFR-18


@lru_cache
def get_settings() -> Settings:
    root = repo_root()
    e = _env(root)
    cfg = yaml.safe_load((root / "e2eai.yaml").read_text(encoding="utf-8"))
    host = "127.0.0.1"
    db = e.get("E2EAI_DB_NAME", "e2eai")
    return Settings(
        tier=cfg["tier"],
        database_url=f"postgresql+asyncpg://{e['POSTGRES_USER']}:{e['POSTGRES_PASSWORD']}@{host}:{e['POSTGRES_PORT']}/{db}",
        valkey_url=f"redis://:{e['VALKEY_PASSWORD']}@{host}:{e['VALKEY_PORT']}/{e.get('E2EAI_VALKEY_DB', '0')}",
        openfga_url=f"http://{host}:{e['OPENFGA_PORT']}",
        openfga_key=e["OPENFGA_PRESHARED_KEY"],
        openfga_store=e.get("E2EAI_OPENFGA_STORE", "e2eai"),
        litellm_url=f"http://{host}:{e['LITELLM_PORT']}",
        litellm_key=e["LITELLM_MASTER_KEY"],
        s3_url=f"http://{host}:{e['S3_PORT']}",
        s3_access_key=e["S3_ACCESS_KEY"],
        s3_secret_key=e["S3_SECRET_KEY"],
        default_language=cfg.get("locale", {}).get("default_language", "id"),
        time_zone=cfg.get("locale", {}).get("time_zone", "Asia/Jakarta"),
    )
