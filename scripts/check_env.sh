#!/usr/bin/env bash
# One-screen health check. Run it every hour and before recording.
IP=${IP:-127.0.0.1}
chk(){ printf "%-28s" "$1"; if curl -fsS -m 3 "$2" >/dev/null 2>&1; then echo "OK   $2"; else echo "DOWN $2"; fi; }
chk "vLLM (super)"      "http://$IP:8000/v1/models"
chk "vLLM (cosmos VLM)" "http://$IP:8001/v1/models"
chk "vLLM (lightning)"  "http://$IP:8002/v1/models"
chk "core"              "http://$IP:8100/health"
chk "perception"        "http://$IP:8150/health"
chk "robot"             "http://$IP:8200/robot/status"
chk "mediamtx (rtsp)"   "http://$IP:8888/"
echo; echo "memory:"; free -h | head -2; command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=memory.used,memory.total --format=csv 2>/dev/null || true
echo; echo "perception state:"; curl -s -m 3 "http://$IP:8150/state" | python3 -c "import sys,json; s=json.load(sys.stdin); print(' fps',s['fps'],'source_ok',s['source_ok'],'counts',s['counts'],'zone',s['zone_states'].get('inspection_zone'))" 2>/dev/null || echo " (down)"
