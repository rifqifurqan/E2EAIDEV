"""Prompt-injection guardrails for retrieved context (FR-C8, FR-T8, FR-O9).

Retrieved documents are untrusted data. The local detector is deterministic/offline; future promptfoo,
garak, or model-classifier checks can plug into the same protocol.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from .core.config import repo_root
from .core.errors import AppError


@dataclass(frozen=True)
class PromptInjectionResult:
    blocked: bool
    reasons: tuple[str, ...] = ()


class PromptInjectionDetector(Protocol):
    def detect(self, text: str) -> PromptInjectionResult: ...


@dataclass(frozen=True)
class PromptGuardPolicy:
    enabled: bool = True
    block_suspicious_context: bool = True
    detector: str = "local"

    @classmethod
    def from_settings(cls) -> "PromptGuardPolicy":
        try:
            import yaml

            cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8")) or {}
            raw = cfg.get("prompt_guard", {}) or {}
            return cls(
                enabled=bool(raw.get("enabled", True)),
                block_suspicious_context=bool(raw.get("block_suspicious_context", True)),
                detector=str(raw.get("detector", "local")),
            )
        except FileNotFoundError:
            return cls()


class LocalPromptInjectionDetector:
    """Rule detector for common indirect prompt injection phrases in retrieved chunks."""

    _rules = (
        ("ignore_instructions", re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions?\b", re.I)),
        ("reveal_secrets", re.compile(r"\b(?:reveal|show|print|dump|leak)\s+(?:the\s+)?(?:secret|secrets|api\s*key|token|password)s?\b", re.I)),
        ("exfiltrate", re.compile(r"\b(?:exfiltrate|send|upload)\s+(?:data|files?|secrets?|tokens?)\b", re.I)),
        ("tool_misuse", re.compile(r"\b(?:call|use|invoke|run)\s+(?:the\s+)?(?:tool|function|shell|terminal|browser)\b", re.I)),
        ("developer_override", re.compile(r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(?:a\s+)?(?:developer|system|admin|root)\b", re.I)),
    )

    def detect(self, text: str) -> PromptInjectionResult:
        reasons = tuple(name for name, pattern in self._rules if pattern.search(text))
        return PromptInjectionResult(blocked=bool(reasons), reasons=reasons)


class ExternalPromptInjectionDetector:
    """Adapter boundary for promptfoo/garak/classifier integrations; not wired in Lite yet."""

    def detect(self, text: str) -> PromptInjectionResult:
        raise AppError(503, "Prompt guard detector unavailable", "External prompt-injection detector is not configured.")


def select_prompt_detector(policy: PromptGuardPolicy | None = None) -> PromptInjectionDetector:
    policy = policy or PromptGuardPolicy.from_settings()
    if policy.detector in ("local", "regex", "rules"):
        return LocalPromptInjectionDetector()
    return ExternalPromptInjectionDetector()
