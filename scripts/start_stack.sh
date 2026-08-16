#!/usr/bin/env bash
# Preflight and start the ForgeMind application services. This script performs
# orchestration only: it does not install packages, download models, or stop
# processes it did not start.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"

CORE_URL="${CORE_URL:-http://127.0.0.1:8100}"
ROBOT_URL="${ROBOT_URL:-http://127.0.0.1:8200}"
PERCEPTION_URL="${PERCEPTION_URL:-http://127.0.0.1:8150}"
PLANNER="${PLANNER:-llm}"
SOURCE="${SOURCE:-rtsp://127.0.0.1:8554/line}"
REQUIRE_VLM="${REQUIRE_VLM:-0}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-30}"

fail() { echo "preflight failed: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 is not installed"; }
http_ok() { curl -fsS --max-time 5 "$1" >/dev/null 2>&1; }

need python
need curl
[ -d .venv ] || fail ".venv is missing; create it and install requirements.txt"
python -c 'import fastapi, uvicorn, cv2' >/dev/null 2>&1 || \
  fail "Python dependencies are unavailable; activate .venv and install requirements.txt"

if [ "$PLANNER" = "llm" ]; then
  [ -n "${LLM_BASE_URL:-}" ] || fail "LLM_BASE_URL is required when PLANNER=llm"
  [ -n "${LLM_MODEL:-}" ] || fail "LLM_MODEL is required when PLANNER=llm"
  http_ok "${LLM_BASE_URL%/}/models" || fail "LLM endpoint is unavailable: ${LLM_BASE_URL%/}/models"
fi

if [ "$REQUIRE_VLM" = "1" ]; then
  [ -n "${VLM_URL:-}" ] || fail "VLM_URL is required when REQUIRE_VLM=1"
  [ -n "${VLM_MODEL:-}" ] || fail "VLM_MODEL is required when REQUIRE_VLM=1"
  http_ok "${VLM_URL%/}/models" || fail "VLM endpoint is unavailable: ${VLM_URL%/}/models"
fi

case "$SOURCE" in
  rtsp://*) need ffprobe; ffprobe -v error -rtsp_transport tcp -i "$SOURCE" -t 1 -f null - >/dev/null 2>&1 || fail "camera stream is unavailable: $SOURCE" ;;
  http://*|https://*) curl -fsS --max-time 5 --range 0-0 "$SOURCE" >/dev/null 2>&1 || fail "camera source is unavailable: $SOURCE" ;;
  0|[0-9]*) : ;;
  *) [ -r "$SOURCE" ] || fail "camera file is not readable: $SOURCE" ;;
esac

export CORE_URL ROBOT_URL PLANNER SOURCE
bash scripts/start_all.sh &
STACK_PID=$!
trap 'kill "$STACK_PID" 2>/dev/null || true; wait "$STACK_PID" 2>/dev/null || true' EXIT INT TERM

deadline=$((SECONDS + STARTUP_TIMEOUT))
while (( SECONDS < deadline )); do
  if http_ok "$CORE_URL/health" && http_ok "$ROBOT_URL/robot/status" && http_ok "$PERCEPTION_URL/health"; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}'); IP=${IP:-127.0.0.1}
    echo "ForgeMind is ready"
    echo "dashboard  http://$IP:8100/dashboard"
    echo "stations   http://$IP:8100/station/alice  /bob  /charlie  /recovery"
    echo "calibrate  http://$IP:8150/calibrate"
    wait "$STACK_PID"
    exit $?
  fi
  kill -0 "$STACK_PID" 2>/dev/null || fail "application stack exited during startup; inspect logs/*.log"
  sleep 1
done

fail "services did not become healthy within ${STARTUP_TIMEOUT}s; inspect logs/*.log"
