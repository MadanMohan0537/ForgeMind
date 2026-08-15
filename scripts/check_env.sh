#!/usr/bin/env bash
# P4 owns this on an hourly cadence all night (per execution plan Section 5).
# Quick health snapshot of the Spark environment: GPU, memory, and whichever
# VLM backend (VSS or Cosmos) is supposed to be up.
set -uo pipefail

echo "=== $(date) ==="

echo "--- GPU ---"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv 2>&1 || echo "nvidia-smi unavailable"

echo "--- Memory ---"
free -h 2>&1 || vm_stat 2>&1

echo "--- VLM backend (\$VLM_URL) ---"
if [ -z "${VLM_URL:-}" ]; then
  echo "VLM_URL not set"
else
  curl -sf -m 5 "${VLM_URL%/}/models" && echo "OK: ${VLM_URL}" || echo "UNREACHABLE: ${VLM_URL}"
fi

echo "--- Disk ---"
df -h / 2>&1
