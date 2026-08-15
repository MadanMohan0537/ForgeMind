#!/usr/bin/env bash
# VLM second opinion WITHOUT the full VSS blueprint (fallback if VSS isn't up by the checkpoint).
# Cosmos-Reason2-8B via vLLM, OpenAI-compatible with image inputs, on :8001.
set -euo pipefail
MODEL="${MODEL:-nvidia/Cosmos-Reason2-8B}"
exec vllm serve "$MODEL" --served-model-name cosmos --host 0.0.0.0 --port "${PORT:-8001}" \
  --gpu-memory-utilization "${GPU_UTIL:-0.18}" --max-model-len 8192 --trust-remote-code \
  --limit-mm-per-prompt '{"image":2}' "$@"
# Perception:  export VLM_URL=http://127.0.0.1:8001/v1 VLM_MODEL=cosmos
