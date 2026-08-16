#!/usr/bin/env bash
# P4: serve the locally downloaded Cosmos Reason2 VLM through vLLM.
# Exposes an OpenAI-compatible endpoint at http://127.0.0.1:8001/v1.
set -euo pipefail

MODEL_DIR="${COSMOS_MODEL_DIR:-$HOME/models/models/llm/nvidia--Cosmos-Reason2-8B}"
IMAGE="${COSMOS_IMAGE:-vllm/vllm-openai:latest}"
CONTAINER="${COSMOS_CONTAINER:-forgemind-cosmos}"
PORT="${COSMOS_PORT:-8001}"

if [ ! -f "$MODEL_DIR/config.json" ]; then
  echo "Cosmos model not found: $MODEL_DIR" >&2
  exit 1
fi

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  if [ "$(docker inspect -f "{{.State.Running}}" "$CONTAINER")" = "true" ]; then
    echo "$CONTAINER is already running"
  else
    docker start "$CONTAINER"
  fi
else
  docker run -d \
    --name "$CONTAINER" \
    --gpus all \
    --ipc=host \
    --restart unless-stopped \
    -p "127.0.0.1:${PORT}:8000" \
    -v "${MODEL_DIR}:/model:ro" \
    "$IMAGE" \
    /model \
    --served-model-name cosmos \
    --trust-remote-code \
    --dtype bfloat16 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.35 \
    --limit-mm-per-prompt "{\"video\":1,\"image\":4}"
fi

echo "Waiting for Cosmos..."
for attempt in $(seq 1 60); do
  if curl -sf --max-time 5 "http://127.0.0.1:${PORT}/v1/models" >/dev/null; then
    echo "Cosmos ready: http://127.0.0.1:${PORT}/v1"
    echo "export VLM_URL=http://127.0.0.1:${PORT}/v1"
    echo "export VLM_MODEL=cosmos"
    exit 0
  fi
  sleep 5
done

echo "Cosmos did not become ready; inspect: docker logs $CONTAINER" >&2
exit 1
