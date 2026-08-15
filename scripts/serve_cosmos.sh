#!/usr/bin/env bash
# P4: fallback VLM serving script — use if VSS blueprint isn't answering
# questions about a sample clip by the 1:00 AM checkpoint.
#
# Runs the NVIDIA Cosmos Reason VLM NIM container locally on the GN100/Spark
# and exposes an OpenAI-compatible endpoint at http://127.0.0.1:8001/v1.
#
# Requires: NGC_API_KEY set, docker + NVIDIA Container Toolkit installed.
set -euo pipefail

: "${NGC_API_KEY:?Set NGC_API_KEY first — get it from https://ngc.nvidia.com}"
# NOTE(P4): confirm the exact NIM image name/tag on build.nvidia.com/nim
# for the Cosmos model you have access to — this is a placeholder.
IMAGE="${COSMOS_IMAGE:-nvcr.io/nim/nvidia/cosmos-reason1-7b:latest}"
PORT="${COSMOS_PORT:-8001}"

echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin

docker run -it --rm \
  --gpus all \
  --shm-size=16GB \
  -e NGC_API_KEY="$NGC_API_KEY" \
  -p "${PORT}:8000" \
  -v "$HOME/.cache/nim:/opt/nim/.cache" \
  "$IMAGE"

# Once running, hand perception the endpoint:
#   export VLM_URL="http://127.0.0.1:${PORT}/v1"
#   export VLM_MODEL="cosmos"
