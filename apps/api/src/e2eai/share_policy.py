"""Sensitivity labels (FR-D5) and share guardrails (FR-S7).

Labels: public/internal/confidential/restricted; upload/create defaults to internal. The admin policy
has safe defaults — external sharing off (local-only), confidential/restricted may never go external,
restricted may never be shared company-wide. `share_block_reason` is pure so it runs *before* any
OpenFGA/doc_principal write; a blocked share creates no grant, only an audit row.
"""

from dataclasses import dataclass

SENSITIVITIES = ("public", "internal", "confidential", "restricted")
DEFAULT_SENSITIVITY = "internal"  # FR-D5 upload/create default

_EXTERNAL_TYPES = frozenset({"guest"})    # external principals (PRD T4, reserved `guest` type)
_COMPANY_WIDE_TYPES = frozenset({"org"})  # company/org-wide audiences


@dataclass(frozen=True)
class SharePolicy:
    allow_external: bool = False                                 # FR-M9 safe default: local-only
    no_external: frozenset = frozenset({"confidential", "restricted"})
    no_company_wide: frozenset = frozenset({"restricted"})

    @classmethod
    def from_settings(cls) -> "SharePolicy":
        """Read the optional `share_policy` block of e2eai.yaml; absent -> safe defaults (external off)."""
        import yaml

        from .core.config import repo_root

        cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8")) or {}
        sp = cfg.get("share_policy") or {}
        return cls(allow_external=bool(sp.get("allow_external", False)))


def principal_type(principal: str) -> str:
    return principal.split(":", 1)[0]


def share_block_reason(sensitivity: str, principal: str, policy: SharePolicy) -> str | None:
    """A human-readable reason the share is blocked by policy, or None if allowed."""
    ptype = principal_type(principal)
    if ptype in _EXTERNAL_TYPES:
        if sensitivity in policy.no_external:
            return f"{sensitivity} documents cannot be shared to external principals"
        if not policy.allow_external:
            return "external sharing is disabled by admin policy"
    if ptype in _COMPANY_WIDE_TYPES and sensitivity in policy.no_company_wide:
        return f"{sensitivity} documents cannot be shared company-wide"
    return None
