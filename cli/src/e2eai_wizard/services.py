"""What the wizard can install. Data only; compose.yaml holds the container definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    label: str
    default_port: int
    port_env: str
    profile: str | None = None  # None = always installed


# Default host ports sit in the 1xxxx range to avoid clashing with local dev servers.
SERVICES = (
    Service("postgres", "PostgreSQL + pgvector", 15432, "POSTGRES_PORT"),
    Service("valkey", "Valkey (Redis-compatible cache/queue)", 16379, "VALKEY_PORT"),
    Service("openfga", "OpenFGA (document permissions)", 18080, "OPENFGA_PORT"),
    Service("seaweedfs", "SeaweedFS (S3 file storage)", 18333, "S3_PORT"),
    Service("litellm", "LiteLLM (model gateway)", 14000, "LITELLM_PORT"),
    Service("ollama", "Ollama (local models)", 21434, "OLLAMA_PORT", profile="ollama"),
    Service("tei-embed", "TEI embeddings", 18081, "TEI_EMBED_PORT", profile="tei-embed"),
    Service("tei-rerank", "TEI reranker", 18082, "TEI_RERANK_PORT", profile="tei-rerank"),
    Service("keycloak", "Keycloak (SSO)", 18180, "KEYCLOAK_PORT", profile="keycloak"),
)
BY_NAME = {s.name: s for s in SERVICES}

# env key -> (owning service, label, required prefix)
SECRETS = {
    "POSTGRES_PASSWORD": ("postgres", "PostgreSQL admin password", ""),
    "OPENFGA_DB_PASSWORD": ("openfga", "OpenFGA database password", ""),
    "LITELLM_DB_PASSWORD": ("litellm", "LiteLLM database password", ""),
    "VALKEY_PASSWORD": ("valkey", "Valkey password", ""),
    "OPENFGA_PRESHARED_KEY": ("openfga", "OpenFGA API key", ""),
    "S3_SECRET_KEY": ("seaweedfs", "S3 secret key", ""),
    "LITELLM_MASTER_KEY": ("litellm", "LiteLLM master key", "sk-"),
    "TEI_API_KEY": ("tei", "TEI API key", ""),
    "KEYCLOAK_DB_PASSWORD": ("keycloak", "Keycloak database password", ""),
    "KEYCLOAK_ADMIN_PASSWORD": ("keycloak", "Keycloak admin password", ""),
}

# env key -> (owning service, label, default)
USERS = {
    "POSTGRES_USER": ("postgres", "PostgreSQL admin username", "e2eai"),
    "S3_ACCESS_KEY": ("seaweedfs", "S3 access key (username)", None),  # None = generated
    "KEYCLOAK_ADMIN_USER": ("keycloak", "Keycloak admin username", "admin"),
}


def enabled_services(answers: dict) -> list[str]:
    """Services that will actually run, in SERVICES order."""
    on = []
    for s in SERVICES:
        if s.profile is None:
            on.append(s.name)
        elif answers["optional"].get(s.name) and not (s.name == "ollama" and answers["host_ollama"]):
            on.append(s.name)
    return on


def owner_enabled(owner: str, enabled: list[str]) -> bool:
    if owner == "tei":
        return "tei-embed" in enabled or "tei-rerank" in enabled
    return owner in enabled
