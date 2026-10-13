"""Supply-chain checks and SBOM generation (NFR-9).

Reads the two inputs that already pin everything: `uv.lock` files (hash-locked Python dependencies) and
`deploy/versions.lock` (container images pinned by digest). It produces a CycloneDX 1.5 SBOM and fails closed when an
image is not pinned by digest or a registry package has no hash. The SBOM is deterministic: no timestamp, no serial
number, no machine data, so the same inputs always give the same file.

Not covered here (needs CI and signing keys): dependency/container vulnerability scanning and signed release artifacts.
"""

from __future__ import annotations

import re
import tomllib

import yaml

_DIGEST = re.compile(r"@sha256:([0-9a-f]{64})$")
_FLOATING_TAGS = {"latest", "stable", "main", "master", "edge", "nightly"}


def parse_uv_lock(text: str) -> list[dict]:
    """Registry packages from a uv.lock: name, version, every sdist/wheel hash. The project itself is skipped."""
    data = tomllib.loads(text)
    packages: list[dict] = []
    for pkg in data.get("package", []):
        if "registry" not in (pkg.get("source") or {}):
            continue  # editable / virtual / path sources are our own code, not third-party artifacts
        hashes: list[str] = []
        sdist = pkg.get("sdist") or {}
        if sdist.get("hash"):
            hashes.append(sdist["hash"])
        hashes += [w["hash"] for w in pkg.get("wheels", []) if w.get("hash")]
        packages.append({"name": pkg["name"], "version": pkg.get("version", ""), "hashes": hashes})
    return packages


def parse_versions_lock(text: str) -> dict[str, str]:
    images = (yaml.safe_load(text) or {}).get("images") or {}
    return {str(k): str(v) for k, v in images.items()}


def check_lock_hashes(packages: list[dict]) -> dict:
    missing = [f"{p['name']}=={p['version']}" for p in packages if not p["hashes"]]
    return {"ok": not missing, "missing": missing, "checked": len(packages)}


def split_image(ref: str) -> dict:
    """`repo/name:tag@sha256:digest` -> name, tag, digest (digest may be None)."""
    digest_match = _DIGEST.search(ref)
    digest = digest_match.group(1) if digest_match else None
    base = ref[: digest_match.start()] if digest_match else ref
    last = base.rsplit("/", 1)[-1]
    if ":" in last:
        name_tail, tag = last.rsplit(":", 1)
        name = base[: len(base) - len(last)] + name_tail
    else:
        name, tag = base, ""
    return {"name": name, "tag": tag, "digest": digest}


def check_images_pinned(images: dict[str, str]) -> dict:
    unpinned = []
    for key, ref in images.items():
        parts = split_image(ref)
        if parts["digest"] is None or parts["tag"] in _FLOATING_TAGS:
            unpinned.append(key)
    return {"ok": not unpinned, "unpinned": unpinned, "checked": len(images)}


def _hashes(values: list[str]) -> list[dict]:
    return [{"alg": "SHA-256", "content": v.split(":", 1)[1]} for v in values if v.startswith("sha256:")]


def build_sbom(*, version: str, python_packages: list[dict], images: dict[str, str]) -> dict:
    components: list[dict] = []
    seen: set[str] = set()
    for pkg in sorted(python_packages, key=lambda p: (p["name"].lower(), p["version"])):
        ref = f"pypi:{pkg['name']}@{pkg['version']}"
        if ref in seen:
            continue
        seen.add(ref)
        comp = {"type": "library", "bom-ref": ref, "name": pkg["name"], "version": pkg["version"],
                "purl": f"pkg:pypi/{pkg['name']}@{pkg['version']}"}
        if pkg["hashes"]:
            comp["hashes"] = _hashes(pkg["hashes"])
        components.append(comp)
    for key, image in sorted(images.items()):
        parts = split_image(image)
        comp = {"type": "container", "bom-ref": f"image:{key}", "name": parts["name"], "version": parts["tag"]}
        if parts["digest"]:
            comp["hashes"] = [{"alg": "SHA-256", "content": parts["digest"]}]
        components.append(comp)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "e2eaidev", "version": version}},
        "components": components,
    }
