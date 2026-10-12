"""FR-M8 model file security: safetensors preferred, pickle scanning, checksum + signature checks.

Everything is static analysis: pickles are never loaded or executed, only their opcodes are read.
"""

import hashlib
import hmac
import io
import pickle
import pickletools

import pytest


def test_format_classification_prefers_safetensors_and_flags_pickle_formats():
    from e2eai.model_file_security import classify_format

    assert classify_format("model.safetensors") == {"format": "safetensors", "risk": "low", "preferred": True}
    assert classify_format("Llama-3.Q4_K_M.gguf")["risk"] == "low"
    for name in ("weights.bin", "model.pt", "model.pth", "ckpt.ckpt", "x.pkl", "x.pickle"):
        info = classify_format(name)
        assert info["risk"] == "high" and info["preferred"] is False, name
    assert classify_format("README.md")["format"] == "unknown"
    assert classify_format("../../etc/passwd.pt")["format"] == "pickle"  # only the basename matters


def test_pickle_scan_flags_dangerous_globals_without_executing_them():
    from e2eai.model_file_security import scan_pickle

    class Evil:
        def __reduce__(self):
            import os
            return (os.system, ("echo should-not-run",))

    evil = pickle.dumps(Evil(), protocol=2)
    result = scan_pickle(evil)
    assert result["safe"] is False
    assert any(f["module"] in {"os", "posix", "nt"} and f["name"] == "system" for f in result["findings"])

    evil4 = pickle.dumps(Evil(), protocol=4)  # STACK_GLOBAL path
    assert scan_pickle(evil4)["safe"] is False

    benign = pickle.dumps({"weights": [1.0, 2.0], "name": "tiny"}, protocol=4)
    ok = scan_pickle(benign)
    assert ok["safe"] is True and ok["findings"] == []

    assert scan_pickle(b"not a pickle at all")["safe"] is False  # unparseable -> fail closed
    assert scan_pickle(b"not a pickle at all")["error"] == "unparseable"


def test_checksum_and_manifest_signature_verification_fail_closed(monkeypatch):
    from e2eai.model_file_security import sign_manifest, verify_checksum, verify_manifest_signature

    data = b"tensor-bytes"
    digest = hashlib.sha256(data).hexdigest()
    assert verify_checksum(data, digest) is True
    assert verify_checksum(data, digest.upper()) is True
    assert verify_checksum(data, "0" * 64) is False
    assert verify_checksum(data, "") is False

    manifest = {"model.safetensors": digest}
    key = b"unit-test-signing-key"
    sig = sign_manifest(manifest, key=key)
    assert verify_manifest_signature(manifest, sig, key=key) is True
    assert verify_manifest_signature(manifest, sig, key=b"other-key") is False
    assert verify_manifest_signature({"model.safetensors": "0" * 64}, sig, key=key) is False
    assert verify_manifest_signature(manifest, "", key=key) is False
    assert verify_manifest_signature(manifest, sig, key=b"") is False


def test_evaluate_model_file_verdicts():
    from e2eai.model_file_security import evaluate_model_file

    data = b"safe-tensor-bytes"
    digest = hashlib.sha256(data).hexdigest()

    allow = evaluate_model_file("m.safetensors", data, expected_sha256=digest)
    assert allow["verdict"] == "allow" and allow["reasons"] == []

    unverified = evaluate_model_file("m.safetensors", data)
    assert unverified["verdict"] == "warn" and "checksum_not_provided" in unverified["reasons"]

    bad_sum = evaluate_model_file("m.safetensors", data, expected_sha256="0" * 64)
    assert bad_sum["verdict"] == "block" and "checksum_mismatch" in bad_sum["reasons"]

    evil_pickle = pickle.dumps(type("E", (), {"__reduce__": lambda self: (__import__("os").system, ("x",))})())
    blocked = evaluate_model_file("w.bin", evil_pickle, expected_sha256=hashlib.sha256(evil_pickle).hexdigest())
    assert blocked["verdict"] == "block" and "pickle_dangerous_globals" in blocked["reasons"]

    benign = pickle.dumps({"a": 1})
    warned = evaluate_model_file("w.pt", benign, expected_sha256=hashlib.sha256(benign).hexdigest())
    assert warned["verdict"] == "warn" and "pickle_format_not_preferred" in warned["reasons"]

    assert "bytes" not in str(allow) and data.decode() not in str(allow)  # no content echoed


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/model-security/evaluate"]
    assert "post" in paths["/api/v1/model-security/scan-pickle"]
