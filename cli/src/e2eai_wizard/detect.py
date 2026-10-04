"""Read the machine: hardware, Docker, an existing Ollama, and which ports are free."""

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Gpu:
    name: str
    vram_gb: float


@dataclass
class Hardware:
    cpus: int
    ram_gb: float
    disk_free_gb: float
    gpu: Gpu | None


def _run(*cmd: str) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _ram_gb() -> float:
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MemoryStatus(dwLength=ctypes.sizeof(MemoryStatus))
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullTotalPhys / 1024**3
    if sys.platform == "darwin":
        return int(_run("sysctl", "-n", "hw.memsize") or 0) / 1024**3
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) / 1024**2
    return 0.0


def _gpu() -> Gpu | None:
    out = _run("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits")
    if not out:
        return None
    name, mib = out.splitlines()[0].rsplit(",", 1)
    return Gpu(name=name.strip(), vram_gb=round(float(mib) / 1024, 1))


def hardware(path: Path = Path.cwd()) -> Hardware:
    return Hardware(
        cpus=os.cpu_count() or 1,
        ram_gb=round(_ram_gb(), 1),
        disk_free_gb=round(shutil.disk_usage(path).free / 1024**3, 1),
        gpu=_gpu(),
    )


def docker_version() -> str | None:
    return _run("docker", "info", "--format", "{{.ServerVersion}}")


def docker_volume_exists(name: str) -> bool:
    return bool(_run("docker", "volume", "ls", "-q", "--filter", f"name=^{name}$"))


def host_ollama_version(url: str = "http://127.0.0.1:11434") -> str | None:
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=1.5) as r:
            return json.load(r).get("version")
    except (OSError, ValueError):
        return None


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return True
    with socket.socket() as s:  # also catches ports Windows reserves for Hyper-V
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def suggest_port(preferred: int, taken: set[int]) -> int:
    for port in range(preferred, 65536):
        if port not in taken and not port_in_use(port):
            return port
    raise RuntimeError(f"no free port at or above {preferred}")


def recommend_tier(ram_gb: float) -> str:
    # PRD §12: Lite targets 16 GB laptops; Standard (CPU) starts at a 64 GB server.
    return "lite" if ram_gb < 48 else "standard"
