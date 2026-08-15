#!/usr/bin/env bash
# Nemotron 3 Super 120B-A12B on vLLM, capped so VSS/Cosmos still fit in the 128 GB pool.
# Adjust MODEL to the local path or HF id you actually have (NVFP4 checkpoint recommended for Spark).
set -euo pipefail
MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4}"      # or /path/to/checkpoint copied from the hard drive
PORT="${PORT:-8000}"
GPU_UTIL="${GPU_UTIL:-0.60}"      # 0.60 * 128GB ≈ 77GB for weights+KV; leaves ~50GB for VSS/Cosmos/OS. Lower if VSS OOMs.
MAXLEN="${MAXLEN:-32768}"
echo "serving $MODEL on :$PORT (gpu_util=$GPU_UTIL max_len=$MAXLEN)"
# If the model card lists extra flags for Spark (moe backend, kv dtype, speculative draft), add them here.
exec vllm serve "$MODEL" \
  --served-model-name super \
  --host 0.0.0.0 --port "$PORT" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --max-model-len "$MAXLEN" \
  --enable-prefix-caching \
  --trust-remote-code \
  --kv-cache-dtype fp8 \
  "$@"
# Smoke test:  curl -s localhost:8000/v1/models | jq
#              python - <<'PY'
#              from services.core import llm; print(llm.health())
#              PY
