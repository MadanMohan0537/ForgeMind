#!/usr/bin/env bash
# Safe default DGX startup: one Ollama Nemotron copy, optional Cosmos, then ForgeMind.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${VIRTUAL_ENV:-}" ]; then
  [ -f .venv/bin/activate ] || {
    echo "No active Python environment and .venv/bin/activate is missing" >&2
    exit 1
  }
  source .venv/bin/activate
fi
export PYTHONPATH="$PWD"

export MODEL_RUNTIME="${MODEL_RUNTIME:-ollama}"
export ROBOT_ADAPTER="${ROBOT_ADAPTER:-human}"
export SOURCE="${SOURCE:-rtsp://127.0.0.1:8554/line}"
export REQUIRE_VLM="${REQUIRE_VLM:-0}"

if [ "$MODEL_RUNTIME" = "ollama" ]; then
  command -v ollama >/dev/null 2>&1 || { echo "ollama is not installed" >&2; exit 1; }
  export PLANNER=llm
  export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
  export LLM_MODEL="${LLM_MODEL:-nemotron-3.5-lightning:latest}"
  export LLM_FAST_MODEL="${LLM_FAST_MODEL:-$LLM_MODEL}"
  export LLM_THINK_MODE=ollama
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null || {
    echo "Ollama is not serving; start 'ollama serve' first" >&2; exit 1;
  }
  ollama run "$LLM_MODEL" "Return only READY" >/dev/null
elif [ "$MODEL_RUNTIME" = "vllm" ]; then
  export PLANNER=llm
  export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8002/v1}"
  export LLM_MODEL="${LLM_MODEL:-lightning}"
  export LLM_FAST_MODEL="${LLM_FAST_MODEL:-$LLM_MODEL}"
  export LLM_THINK_MODE=kwarg
elif [ "$MODEL_RUNTIME" = "none" ]; then
  export PLANNER=rule
else
  echo "MODEL_RUNTIME must be ollama, vllm, or none" >&2
  exit 2
fi

PREFLIGHT_ARGS=(--llm "$MODEL_RUNTIME")
if [ "$REQUIRE_VLM" = "1" ]; then PREFLIGHT_ARGS+=(--require-vlm); fi
python scripts/dgx_preflight.py "${PREFLIGHT_ARGS[@]}"

if [ "$REQUIRE_VLM" = "1" ]; then
  export VLM_URL="${VLM_URL:-http://127.0.0.1:8001/v1}"
  export VLM_MODEL="${VLM_MODEL:-cosmos}"
fi

exec bash scripts/start_stack.sh
