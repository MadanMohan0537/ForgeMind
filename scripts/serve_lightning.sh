#!/usr/bin/env bash
# OPTIONAL fast model for the per-kit action loop (+ Lightning bounty). Only start if `free -h` shows ~25GB headroom.
# Recipe from the NVFP4 model card (DSpark speculative decoding, tuned for DGX Spark). Uses port 8002.
set -euo pipefail
MODEL_CKPT="${MODEL_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4}"
DSPARK_CKPT="${DSPARK_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark}"
exec vllm serve "$MODEL_CKPT" --served-model-name lightning --port "${PORT:-8002}" --host 0.0.0.0 \
  --gpu-memory-utilization "${GPU_UTIL:-0.15}" --max-model-len 32768 \
  --moe-backend marlin --kv-cache-dtype fp8 --enable-prefix-caching --trust-remote-code \
  --mamba-backend flashinfer --mamba-cache-mode align --reasoning-parser nemotron_v3 \
  --speculative_config.method dspark --speculative_config.model "$DSPARK_CKPT" --speculative_config.num_speculative_tokens 3 \
  "$@"
# Then, for core:  export LLM_FAST_MODEL=lightning LLM_FAST_BASE_URL=http://127.0.0.1:8002/v1
