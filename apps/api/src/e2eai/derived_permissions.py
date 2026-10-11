"""FR-C6 Derived content inherits the strictest permissions of its sources.

Pure/offline helpers that compute the effective permission level from one or more source documents
without expanding principals per user or widening access. Only the granted principal identifiers and
the effective strictest level are exposed; raw per-user grants are never expanded or leaked.
"""

from collections import OrderedDict
from collections.abc import Sequence

_ALLOWED_LEVELS = {"owner", "editor", "viewer"}
_LEVEL_ORDER = {"viewer": 0, "editor": 1, "owner": 2}
_PUBLIC_LEVELS = {"viewer"}


def _normalize_level(level: object) -> str:
    normalized = str(level or "").strip().lower()
    if normalized not in _ALLOWED_LEVELS:
        raise ValueError(f"Invalid permission level: {level!r}")
    return normalized


def inherit_strictest(source_grants: Sequence[dict]) -> str:
    """Return the strictest (lowest) permission level across sources (FR-C6).

    Sources wider than the strictest are downgraded; the result never widens access. Unknown levels
    raise before returning so a misconfiguration fails closed rather than weakening security.
    """
    levels = [_normalize_level(grant.get("level")) for grant in source_grants]
    if not levels:
        return "viewer"
    return min(levels, key=lambda level: _LEVEL_ORDER[level])


def compute_derived_permissions(
    *,
    source_ids: Sequence[str],
    source_levels: dict[str, list[dict]],
    include_individual_users: bool = False,
) -> dict:
    """Compute derived-content permissions from source documents (FR-C6).

    `source_levels` maps each source id to its list of granted principal dicts
    (``{principal, level}``). The effective level is the strictest level across all sources.

    By default (include_individual_users=False) the returned `granted_principals` lists the raw
    principal identifiers as stored (teams, divisions, roles) but does NOT expand per-user grants,
    so a derived artifact can never widen access beyond the strictest source. The `effective_level`
    is the strictest of the source levels.
    """
    all_grants: list[dict] = []
    for source_id in source_ids:
        all_grants.extend(source_levels.get(source_id, []))

    effective_level = inherit_strictest(all_grants)

    granted: list[str] = []
    seen: set[str] = set()
    for grant in all_grants:
        principal = str(grant.get("principal") or "")
        if principal in seen:
            continue
        if not include_individual_users and principal.startswith("user:"):
            continue
        seen.add(principal)
        granted.append(principal)

    return {
        "sources": list(source_ids),
        "effective_level": effective_level,
        "granted_principals": granted,
        "inheritance_policy": "strictest_source_wins",
    }
