#!/usr/bin/env python3
"""Validate that all required P0 docs and runbooks exist and contain required headings.

Run:  python scripts/validate_docs.py          (exit 0 = pass, 1 = fail)
  or: cd apps/api && uv run pytest ../../scripts/validate_docs.py -q

Requirement IDs: FR-F22, FR-F14, FR-O13.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

# ---------------------------------------------------------------------------
# Required files and their mandatory headings
# ---------------------------------------------------------------------------

REQUIRED_DOCS: dict[str, list[str]] = {
    "en/user-guide.md": [
        "Getting Started",
        "Document Upload",
        "Sharing",
        "Chat",
    ],
    "id/panduan-pengguna.md": [
        "Memulai",
        "Unggah Dokumen",
        "Berbagi",
        "Chat",
    ],
    "en/admin-operator-guide.md": [
        "Installation",
        "Configuration",
        "Backup",
        "Monitoring",
        "User Management",
    ],
    "id/panduan-admin-operator.md": [
        "Instalasi",
        "Konfigurasi",
        "Pencadangan",
        "Pemantauan",
        "Manajemen Pengguna",
    ],
}

RUNBOOK_HEADINGS = ["Symptoms", "Diagnosis", "Fix", "Verification"]

REQUIRED_RUNBOOKS: list[str] = [
    "runbooks/service-down.md",
    "runbooks/restore-from-backup.md",
    "runbooks/model-endpoint-failing.md",
    "runbooks/vector-store-degraded.md",
    "runbooks/permission-sync-lag.md",
    "runbooks/disk-full.md",
    "runbooks/leaked-key.md",
]


def _headings_in(text: str) -> list[str]:
    """Extract markdown heading text (any level)."""
    return [m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)]


def validate() -> list[str]:
    errors: list[str] = []

    # --- user/admin docs ---
    for relpath, required_headings in REQUIRED_DOCS.items():
        fpath = DOCS / relpath
        if not fpath.is_file():
            errors.append(f"MISSING file: docs/{relpath}")
            continue
        content = fpath.read_text(encoding="utf-8")
        headings = _headings_in(content)
        for h in required_headings:
            if not any(h.lower() in hd.lower() for hd in headings):
                errors.append(f"docs/{relpath}: missing heading containing '{h}'")

    # --- runbooks ---
    for relpath in REQUIRED_RUNBOOKS:
        fpath = DOCS / relpath
        if not fpath.is_file():
            errors.append(f"MISSING file: docs/{relpath}")
            continue
        content = fpath.read_text(encoding="utf-8")
        headings = _headings_in(content)
        for h in RUNBOOK_HEADINGS:
            if not any(h.lower() in hd.lower() for hd in headings):
                errors.append(f"docs/{relpath}: missing heading containing '{h}'")

    return errors


# ---------------------------------------------------------------------------
# pytest entry point
# ---------------------------------------------------------------------------

def test_docs_complete():
    errors = validate()
    assert not errors, "Documentation validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    errors = validate()
    if errors:
        print("FAIL — documentation validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("PASS — all required docs and runbooks present with required headings.")
        sys.exit(0)
