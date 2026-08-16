"""Fail-fast DGX readiness checks for ForgeMind.

This script is read-only: it never starts containers, downloads models, or
changes system settings. Run it before loading models and again before a demo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def http_json(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return True, json.dumps(data)[:240]
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, str(exc)


def available_gib(meminfo: str) -> float:
    for line in meminfo.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    raise ValueError("MemAvailable is missing from /proc/meminfo")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=("ollama", "vllm", "none"), default="ollama")
    parser.add_argument("--require-vlm", action="store_true")
    parser.add_argument("--minimum-free-gib", type=float, default=20.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks: list[Check] = []
    for command in ("git", "docker", "curl", "ffmpeg", "nvidia-smi"):
        path = shutil.which(command)
        checks.append(Check(command, bool(path), path or "not found"))

    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        free = available_gib(meminfo_path.read_text())
        checks.append(Check("memory", free >= args.minimum_free_gib,
                            f"{free:.1f} GiB available; minimum {args.minimum_free_gib:.1f} GiB"))
    else:
        checks.append(Check("memory", False, "/proc/meminfo is unavailable"))

    gpu = subprocess.run(["nvidia-smi"], capture_output=True, text=True) if shutil.which("nvidia-smi") else None
    checks.append(Check("NVIDIA GPU", bool(gpu and gpu.returncode == 0),
                        (gpu.stdout if gpu and gpu.returncode == 0 else gpu.stderr if gpu else "nvidia-smi missing")[:240]))

    ollama_ok, ollama_detail = http_json("http://127.0.0.1:11434/api/ps")
    vllm_ok, vllm_detail = http_json("http://127.0.0.1:8002/v1/models")
    if ollama_ok and vllm_ok:
        checks.append(Check("single Nemotron runtime", False,
                            "Ollama and Lightning vLLM are both active; unload one copy"))
    elif args.llm == "ollama":
        checks.append(Check("Ollama", ollama_ok, ollama_detail))
    elif args.llm == "vllm":
        checks.append(Check("Lightning vLLM", vllm_ok, vllm_detail))

    cosmos_ok, cosmos_detail = http_json("http://127.0.0.1:8001/v1/models")
    checks.append(Check("Cosmos", cosmos_ok, cosmos_detail, required=args.require_vlm))

    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        for check in checks:
            status = "OK" if check.ok else "FAIL" if check.required else "OPTIONAL"
            print(f"{status:8} {check.name:24} {check.detail}")

    return 1 if any(check.required and not check.ok for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
