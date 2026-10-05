"""PII discovery and masking boundary (FR-D6, FR-O12, FR-O9).

The MVP detector is deterministic and offline. It deliberately stores only types/counts in audit paths;
raw matched values are for immediate masking only and must not be logged.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .core.config import repo_root
from .core.errors import AppError

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?62[\s-]?|0)8[0-9][0-9\s-]{6,15}[0-9](?!\w)")
_NIK = re.compile(r"\b\d{16}\b")
_ACCOUNT = re.compile(r"\b\d[\d -]{8,18}\d\b")


@dataclass(frozen=True)
class PiiFinding:
    type: str
    start: int
    end: int
    text: str


class PiiDetector(Protocol):
    def detect(self, text: str) -> list[PiiFinding]: ...


@dataclass(frozen=True)
class PiiPolicy:
    """PII guardrail config with safe local defaults.

    Detecting is on by default; document text is not redacted unless configured, while trace/log masking
    is on so audit/log-safe helpers never need raw PII.
    """

    detect: bool = True
    redact_document_text: bool = False
    mask_traces: bool = True
    detector: str = "regex"

    @classmethod
    def from_settings(cls) -> "PiiPolicy":
        try:
            import yaml

            cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8")) or {}
            raw = cfg.get("pii", {}) or {}
            return cls(
                detect=bool(raw.get("detect", True)),
                redact_document_text=bool(raw.get("redact_document_text", False)),
                mask_traces=bool(raw.get("mask_traces", True)),
                detector=str(raw.get("detector", "regex")),
            )
        except FileNotFoundError:
            return cls()


class RegexPiiDetector:
    """Local deterministic detector for the P1 MVP: emails, Indonesian phones, NIK, account-like IDs."""

    _patterns = (
        ("email", _EMAIL),
        ("phone", _PHONE),
        ("nik", _NIK),
        ("account_number", _ACCOUNT),
    )
    _priority = {"email": 0, "phone": 1, "nik": 2, "account_number": 3}

    def detect(self, text: str) -> list[PiiFinding]:
        candidates: list[PiiFinding] = []
        for typ, pattern in self._patterns:
            for m in pattern.finditer(text):
                candidates.append(PiiFinding(typ, m.start(), m.end(), m.group(0)))
        # Prefer earlier/specific patterns and drop overlaps (NIK should not also become account_number).
        candidates.sort(key=lambda f: (f.start, self._priority[f.type], -(f.end - f.start)))
        accepted: list[PiiFinding] = []
        occupied: list[range] = []
        for finding in candidates:
            span = range(finding.start, finding.end)
            if any(finding.start < r.stop and finding.end > r.start for r in occupied):
                continue
            accepted.append(finding)
            occupied.append(span)
        return accepted


class PresidioPiiDetector:
    """Adapter boundary for Presidio deployments; tests stay offline when the dependency is absent."""

    def detect(self, text: str) -> list[PiiFinding]:
        try:
            from presidio_analyzer import AnalyzerEngine
        except ImportError as exc:
            raise AppError(503, "PII detector unavailable", "Presidio is not installed in this deployment.") from exc
        analyzer = AnalyzerEngine()
        results = analyzer.analyze(text=text, language="en")
        return [PiiFinding(r.entity_type.lower(), r.start, r.end, text[r.start:r.end]) for r in results]


def select_detector(policy: PiiPolicy | None = None) -> PiiDetector:
    policy = policy or PiiPolicy.from_settings()
    return PresidioPiiDetector() if policy.detector == "presidio" else RegexPiiDetector()


def pii_counts(findings: list[PiiFinding]) -> dict[str, int]:
    return dict(Counter(f.type for f in findings))


def mask_text(text: str, findings: list[PiiFinding] | None = None) -> str:
    findings = findings if findings is not None else RegexPiiDetector().detect(text)
    masked = text
    for f in sorted(findings, key=lambda item: item.start, reverse=True):
        masked = masked[:f.start] + f"[{f.type.upper()}]" + masked[f.end:]
    return masked
