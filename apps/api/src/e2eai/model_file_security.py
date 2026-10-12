"""Model file security (FR-M8): safetensors preferred, pickle scanning, checksum/signature checks.

All checks are static. Pickle files are never loaded or executed: only their opcode stream is
read with `pickletools.genops`, and any import of a dangerous module/callable is reported.
Unparseable pickles fail closed. Results never echo file content.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import pickletools
import posixpath
import zipfile
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import User, get_session

SAFE_EXTENSIONS = {".safetensors": "safetensors", ".gguf": "gguf"}
PICKLE_EXTENSIONS = {".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle"}

DANGEROUS_MODULES = frozenset({
    "os", "posix", "nt", "subprocess", "sys", "socket", "shutil", "pty", "importlib", "runpy",
    "ctypes", "multiprocessing", "webbrowser", "urllib", "http", "requests", "pickle", "marshal",
    "code", "codeop", "commands", "popen2", "tempfile", "pathlib", "builtins", "__builtin__",
})
# builtins members that are harmless for tensors/containers; anything else in builtins is flagged.
SAFE_BUILTINS = frozenset({"set", "frozenset", "bytearray", "complex", "slice", "range", "int", "float", "str", "bool", "list", "dict", "tuple", "object"})
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def classify_format(filename: str) -> dict[str, Any]:
    base = posixpath.basename((filename or "").replace("\\", "/")).lower()
    ext = posixpath.splitext(base)[1]
    if ext in SAFE_EXTENSIONS:
        return {"format": SAFE_EXTENSIONS[ext], "risk": "low", "preferred": True}
    if ext in PICKLE_EXTENSIONS:
        return {"format": "pickle", "risk": "high", "preferred": False}
    return {"format": "unknown", "risk": "unknown", "preferred": False}


def _scan_pickle_stream(data: bytes) -> list[dict[str, str]]:
    """Return dangerous/unresolved globals found in one pickle opcode stream."""
    findings: list[dict[str, str]] = []
    strings: list[Any] = []  # recent pushed strings (None marks an unresolved value)
    memo: dict[int, Any] = {}
    memo_counter = 0

    def flag(module: str, name: str) -> None:
        root = module.split(".")[0]
        if module in DANGEROUS_MODULES or root in DANGEROUS_MODULES:
            if module in {"builtins", "__builtin__"} and name in SAFE_BUILTINS:
                return
            findings.append({"module": module, "name": name})

    for opcode, arg, _pos in pickletools.genops(data):
        op = opcode.name
        if op in {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE", "SHORT_BINSTRING", "BINSTRING", "STRING"}:
            strings.append(arg if isinstance(arg, str) else str(arg))
        elif op == "MEMOIZE":
            memo[memo_counter] = strings[-1] if strings else None
            memo_counter += 1
        elif op in {"BINPUT", "LONG_BINPUT"}:
            memo[int(arg)] = strings[-1] if strings else None
        elif op in {"BINGET", "LONG_BINGET"}:
            strings.append(memo.get(int(arg)))
        elif op == "GLOBAL":
            module, _, name = str(arg).partition(" ")
            flag(module, name)
        elif op == "STACK_GLOBAL":
            if len(strings) >= 2 and isinstance(strings[-1], str) and isinstance(strings[-2], str):
                flag(strings[-2], strings[-1])
            else:
                findings.append({"module": "<unresolved>", "name": "<unresolved>"})
            strings = strings[:-2]
        elif op in {"INST", "OBJ"} and isinstance(arg, str):
            module, _, name = arg.partition(" ")
            flag(module, name)
    return findings


def scan_pickle(data: bytes) -> dict[str, Any]:
    """Statically scan a pickle (or a torch zip checkpoint's *.pkl members). Never executes code."""
    streams: list[bytes] = []
    try:
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                streams = [archive.read(n) for n in archive.namelist() if n.endswith(".pkl")]
            if not streams:
                return {"safe": False, "findings": [], "error": "unparseable"}
        else:
            streams = [data]
        findings: list[dict[str, str]] = []
        for stream in streams:
            findings.extend(_scan_pickle_stream(stream))
    except Exception:  # noqa: BLE001 - any parse problem fails closed
        return {"safe": False, "findings": [], "error": "unparseable"}
    unique = [dict(t) for t in sorted({tuple(sorted(f.items())) for f in findings})]
    return {"safe": not unique, "findings": unique, "error": None}


def verify_checksum(data: bytes, expected_sha256: str | None) -> bool:
    expected = (expected_sha256 or "").strip().lower()
    if len(expected) != 64:
        return False
    return hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected)


def _canonical(manifest: dict[str, str]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()


def sign_manifest(manifest: dict[str, str], *, key: bytes) -> str:
    """HMAC-SHA256 over the canonical checksum manifest (filename -> sha256)."""
    if not key:
        raise ValueError("signing key required")
    return hmac.new(key, _canonical(manifest), hashlib.sha256).hexdigest()


def verify_manifest_signature(manifest: dict[str, str], signature: str | None, *, key: bytes) -> bool:
    if not key or not signature:
        return False
    return hmac.compare_digest(sign_manifest(manifest, key=key), signature.strip().lower())


def evaluate_model_file(filename: str, data: bytes, *, expected_sha256: str | None = None) -> dict[str, Any]:
    """Combine format, checksum, and pickle checks into allow / warn / block."""
    fmt = classify_format(filename)
    reasons: list[str] = []
    block = False
    if expected_sha256 is None:
        reasons.append("checksum_not_provided")
    elif not verify_checksum(data, expected_sha256):
        reasons.append("checksum_mismatch")
        block = True
    scan: dict[str, Any] | None = None
    if fmt["format"] == "pickle":
        scan = scan_pickle(data)
        if scan["error"]:
            reasons.append("pickle_unparseable")
            block = True
        elif not scan["safe"]:
            reasons.append("pickle_dangerous_globals")
            block = True
        reasons.append("pickle_format_not_preferred")
    elif fmt["format"] == "unknown":
        reasons.append("unknown_format")
    verdict = "block" if block else ("warn" if reasons else "allow")
    return {
        "filename": posixpath.basename((filename or "").replace("\\", "/")),
        "format": fmt["format"],
        "risk": fmt["risk"],
        "verdict": verdict,
        "reasons": reasons,
        "pickle_findings": scan["findings"] if scan else [],
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class EvaluateIn(BaseModel):
    filename: str
    content_b64: str
    expected_sha256: str | None = None


class ScanPickleIn(BaseModel):
    content_b64: str


router = APIRouter(prefix="/api/v1/model-security", tags=["model-security"])


def _decode(content_b64: str) -> bytes:
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError(400, "content_b64 is not valid base64") from exc
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(413, "Model file too large for inline scan")
    return data


async def _require_admin(db: AsyncSession, sess: dict) -> None:
    import uuid

    from .legal_hold import is_admin

    require_scope(sess, "admin")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active" or not await is_admin(db, user):
        raise AppError(403, "Not allowed")


@router.post("/evaluate")
async def evaluate_api(
    body: EvaluateIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-M8: format + checksum + pickle verdict for a model file (admin only)."""
    await _require_admin(db, sess)
    return evaluate_model_file(body.filename, _decode(body.content_b64), expected_sha256=body.expected_sha256)


@router.post("/scan-pickle")
async def scan_pickle_api(
    body: ScanPickleIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-M8: static pickle opcode scan (never executes the pickle)."""
    await _require_admin(db, sess)
    return scan_pickle(_decode(body.content_b64))
