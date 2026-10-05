"""Malware scanning on upload (FR-D14). Infected files are quarantined and never parsed/indexed.

The Lite default has no AV service (the 5 GB Docker VM can't host one), so the safe default is a local
no-op scanner that passes local uploads through as clean. A configured ClamAV daemon is an adapter
boundary (ClamAV is GPL and runs as its own service, PRD §9): we talk to it with the clamd INSTREAM
protocol over a raw socket, so no new dependency is added. When a *configured* scanner is unavailable,
the safe policy from config decides: fail closed (quarantine, don't parse) or mark pending (retry later).
The guardrail runs before parse/index in `ingest.ingest_version`; the scanner is injectable like the
embedder, so the infected/unavailable branches are tested without a live daemon.
"""

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ScanResult:
    verdict: str  # "clean" | "infected" | "unavailable"
    signature: str | None = None


class Scanner(Protocol):
    async def scan(self, data: bytes) -> ScanResult: ...


@dataclass(frozen=True)
class ScanPolicy:
    enabled: bool = False                 # Lite default: no AV service -> LocalNoopScanner
    on_unavailable: str = "fail_closed"   # safe default; "pending" to retry later
    host: str = "127.0.0.1"
    port: int = 3310                      # clamd default

    @classmethod
    def from_settings(cls) -> "ScanPolicy":
        """Read the optional `malware_scan` block of e2eai.yaml; absent -> safe defaults (off, fail-closed)."""
        import yaml

        from .core.config import repo_root

        cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8")) or {}
        ms = cfg.get("malware_scan") or {}
        on_unavailable = ms.get("on_unavailable", "fail_closed")
        if on_unavailable not in ("fail_closed", "pending"):
            on_unavailable = "fail_closed"
        return cls(
            enabled=bool(ms.get("enabled", False)),
            on_unavailable=on_unavailable,
            host=str(ms.get("host", "127.0.0.1")),
            port=int(ms.get("port", 3310)),
        )


class LocalNoopScanner:
    """Default for Lite local dev: no AV service available, so local uploads pass as clean."""

    async def scan(self, data: bytes) -> ScanResult:
        return ScanResult("clean")


def parse_clamd_response(line: str) -> ScanResult:
    """Parse a clamd INSTREAM reply. `stream: OK` is clean; `stream: <sig> FOUND` is infected."""
    body = line.split(":", 1)[1].strip() if ":" in line else line.strip()
    if body.endswith("FOUND"):
        return ScanResult("infected", body[: -len("FOUND")].strip() or None)
    if body == "OK":
        return ScanResult("clean")
    return ScanResult("unavailable")


@dataclass(frozen=True)
class ClamAVScanner:
    """Adapter boundary to a ClamAV daemon over the clamd INSTREAM protocol (FR-D14).

    A connection/protocol error returns `unavailable` so the caller applies the fail-closed/pending
    policy instead of silently treating an unscanned file as clean."""

    host: str = "127.0.0.1"
    port: int = 3310
    timeout: float = 30.0

    async def scan(self, data: bytes) -> ScanResult:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except (OSError, asyncio.TimeoutError):
            return ScanResult("unavailable")
        try:
            writer.write(b"zINSTREAM\x00")
            # INSTREAM: length-prefixed chunks, terminated by a zero-length chunk.
            writer.write(len(data).to_bytes(4, "big") + data + b"\x00\x00\x00\x00")
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
            raw = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
        except (OSError, asyncio.TimeoutError):
            return ScanResult("unavailable")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        return parse_clamd_response(raw.decode("utf-8", errors="ignore").strip("\x00").strip())


def select_scanner(policy: ScanPolicy) -> Scanner:
    if not policy.enabled:
        return LocalNoopScanner()
    return ClamAVScanner(host=policy.host, port=policy.port)
