#!/usr/bin/env bash
# One-screen Spark health snapshot. P4 runs this hourly and before recording.
set -uo pipefail

IP="${IP:-127.0.0.1}"
VLM_HEALTH_URL="${VLM_URL:-http://${IP}:8001/v1}"

check() {
  printf "%-28s" "$1"
  if curl -fsS -m 3 "$2" >/dev/null 2>&1; then
    echo "OK   $2"
  else
    echo "DOWN $2"
  fi
}

echo "=== $(date) ==="
check "vLLM (super)"      "http://${IP}:8000/v1/models"
check "VLM (VSS/Cosmos)" "${VLM_HEALTH_URL%/}/models"
check "vLLM (lightning)"  "http://${IP}:8002/v1/models"
check "Ollama"            "http://${IP}:11434/api/tags"
check "core"              "http://${IP}:8100/health"
check "perception"        "http://${IP}:8150/health"
check "robot"             "http://${IP}:8200/robot/status"
check "mediamtx (RTSP)"   "http://${IP}:8888/"

echo
echo "GPU:"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv 2>&1 || true
  nvidia-smi 2>&1 | head -20 || true
else
  echo "nvidia-smi unavailable"
fi

echo
echo "memory:"
free -h 2>&1 | head -2 || true

echo
echo "disk:"
df -h / 2>&1 | tail -1 || true

echo
echo "perception state:"
curl -s -m 3 "http://${IP}:8150/state" | python3 -c \
  "import sys,json; s=json.load(sys.stdin); print(' fps',s['fps'],'source_ok',s['source_ok'],'counts',s['counts'],'zone',s['zone_states'].get('inspection_zone'),'vlm',s['vlm_available'])" \
  2>/dev/null || echo " (down)"
