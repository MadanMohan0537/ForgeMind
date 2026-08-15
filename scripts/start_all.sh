#!/usr/bin/env bash
# Start core + robot + perception (+ agent watcher). Logs in ./logs. Ctrl-C stops everything.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
export SOURCE="${SOURCE:-rtsp://127.0.0.1:8554/line}"
export ROBOT_ADAPTER="${ROBOT_ADAPTER:-human}"
export PLANNER="${PLANNER:-llm}"
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export LLM_MODEL="${LLM_MODEL:-super}"
mkdir -p logs
uvicorn services.core.main:app --host 0.0.0.0 --port 8100 > logs/core.log 2>&1 &   P1=$!
uvicorn services.robot.main:app --host 0.0.0.0 --port 8200 > logs/robot.log 2>&1 & P2=$!
uvicorn services.perception.main:app --host 0.0.0.0 --port 8150 > logs/perception.log 2>&1 & P3=$!
if [ "${AGENT_WATCH:-0}" = "1" ]; then python -m services.agent.agent_loop --watch > logs/agent.log 2>&1 & P4=$!; fi
trap 'kill $P1 $P2 $P3 ${P4:-} 2>/dev/null || true' EXIT
sleep 2
IP=$(hostname -I 2>/dev/null | awk '{print $1}'); IP=${IP:-localhost}
echo "dashboard    http://$IP:8100/dashboard"
echo "stations     http://$IP:8100/station/alice  /bob  /charlie  /recovery"
echo "calibrate    http://$IP:8150/calibrate"
echo "logs         tail -f logs/*.log"
wait
