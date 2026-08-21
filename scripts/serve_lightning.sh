#!/usr/bin/env bash
# Nemotron 3.5 Lightning NVFP4 + its DSpark draft model on one DGX Spark.
# Exposes an OpenAI-compatible endpoint at http://127.0.0.1:8002/v1.
set -euo pipefail

MODEL_CKPT="${MODEL_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4}"
DSPARK_CKPT="${DSPARK_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark}"
SERVED_MODEL="${SERVED_MODEL:-lightning}"
LIGHTNING_PORT="${LIGHTNING_PORT:-8002}"
LIGHTNING_RUNTIME="${LIGHTNING_RUNTIME:-auto}"
LIGHTNING_IMAGE="${LIGHTNING_IMAGE:-vllm/vllm-openai:v0.27.1}"
LIGHTNING_CONTAINER="${LIGHTNING_CONTAINER:-forgemind-lightning}"
LIGHTNING_BIND_ADDRESS="${LIGHTNING_BIND_ADDRESS:-127.0.0.1}"
LIGHTNING_HF_CACHE="${LIGHTNING_HF_CACHE:-$HOME/.cache/huggingface}"

# ForgeMind only needs 8K context and low concurrency. This leaves unified-memory
# headroom for Cosmos, the services, and the OS instead of taking the model-card's
# 0.91 allocation intended for a standalone 1M-context server.
LIGHTNING_GPU_UTIL="${LIGHTNING_GPU_UTIL:-0.40}"
LIGHTNING_MAX_MODEL_LEN="${LIGHTNING_MAX_MODEL_LEN:-8192}"
LIGHTNING_MAX_NUM_SEQS="${LIGHTNING_MAX_NUM_SEQS:-2}"
LIGHTNING_SPECULATIVE_TOKENS="${LIGHTNING_SPECULATIVE_TOKENS:-3}"

if ! [[ "$LIGHTNING_GPU_UTIL" =~ ^0\.[0-9]+$|^1\.0$ ]]; then
  echo "LIGHTNING_GPU_UTIL must be between 0 and 1 (received: $LIGHTNING_GPU_UTIL)" >&2
  exit 2
fi
if ! [[ "$LIGHTNING_PORT" =~ ^[1-9][0-9]*$ && "$LIGHTNING_MAX_MODEL_LEN" =~ ^[1-9][0-9]*$ && "$LIGHTNING_MAX_NUM_SEQS" =~ ^[1-9][0-9]*$ && "$LIGHTNING_SPECULATIVE_TOKENS" =~ ^[1-9][0-9]*$ ]]; then
  echo "LIGHTNING_PORT and Lightning size/count settings must be positive integers" >&2
  exit 2
fi

SERVER_ARGS=(
  --model "$MODEL_CKPT"
  --served-model-name "$SERVED_MODEL"
  --host 0.0.0.0
  --port "$LIGHTNING_PORT"
  --moe-backend marlin
  --kv-cache-dtype fp8
  --enable-prefix-caching
  --gpu-memory-utilization "$LIGHTNING_GPU_UTIL"
  --max-model-len "$LIGHTNING_MAX_MODEL_LEN"
  --max-num-seqs "$LIGHTNING_MAX_NUM_SEQS"
  --mamba-backend flashinfer
  --mamba-cache-mode align
  --reasoning-parser nemotron_v3
  --speculative_config.model "$DSPARK_CKPT"
  --speculative_config.num_speculative_tokens "$LIGHTNING_SPECULATIVE_TOKENS"
  --tool-call-parser qwen3_coder
  --enable-auto-tool-choice
)

if [ "$LIGHTNING_RUNTIME" = "auto" ]; then
  if command -v vllm >/dev/null 2>&1; then
    LIGHTNING_RUNTIME=vllm
  elif command -v docker >/dev/null 2>&1; then
    LIGHTNING_RUNTIME=docker
  else
    echo "Neither vllm nor docker is installed" >&2
    exit 127
  fi
fi

if [ "$LIGHTNING_RUNTIME" = "vllm" ]; then
  COMMAND=(vllm serve "${SERVER_ARGS[@]}")
elif [ "$LIGHTNING_RUNTIME" = "docker" ]; then
  COMMAND=(
    docker run --rm --name "$LIGHTNING_CONTAINER"
    --gpus all --ipc=host
    -p "${LIGHTNING_BIND_ADDRESS}:${LIGHTNING_PORT}:${LIGHTNING_PORT}"
    -v "${LIGHTNING_HF_CACHE}:/root/.cache/huggingface"
  )
  if [ -n "${HF_TOKEN:-}" ]; then
    COMMAND+=(-e HF_TOKEN)
  fi
  COMMAND+=("$LIGHTNING_IMAGE" "${SERVER_ARGS[@]}")
else
  echo "LIGHTNING_RUNTIME must be auto, vllm, or docker (received: $LIGHTNING_RUNTIME)" >&2
  exit 2
fi

if [ "${1:-}" = "--print-command" ]; then
  printf '%q' "${COMMAND[0]}"
  printf ' %q' "${COMMAND[@]:1}"
  printf '\n'
  exit 0
fi

if [ "$LIGHTNING_RUNTIME" = "docker" ]; then
  mkdir -p "$LIGHTNING_HF_CACHE"
fi

echo "Serving $MODEL_CKPT + $DSPARK_CKPT as '$SERVED_MODEL' via $LIGHTNING_RUNTIME"
echo "ForgeMind: LLM_BASE_URL=http://127.0.0.1:$LIGHTNING_PORT/v1 LLM_MODEL=$SERVED_MODEL LLM_THINK_MODE=kwarg"
exec "${COMMAND[@]}" "$@"
