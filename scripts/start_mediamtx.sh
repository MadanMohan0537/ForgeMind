#!/usr/bin/env bash
# Phone camera -> RTSP on the Spark. One stream, two consumers (VSS + OpenCV).
# 1) Phone app: Larix Broadcaster (iOS/Android, free) -> Connections -> New -> URL: rtsp://<SPARK_IP>:8554/line  (mode: publish)
#    Lock exposure/white balance in the app, plug the phone in, disable auto-lock. 1080p or 720p, 25-30 fps.
# 2) Fallback (Android): IP Webcam app -> perception can read http://<PHONE_IP>:8080/video directly, and
#    ffmpeg can rewrap it to RTSP for VSS (command at the bottom).
set -euo pipefail
cd "$(dirname "$0")"
ARCH=$(uname -m); case "$ARCH" in aarch64|arm64) A=linux_arm64v8;; x86_64) A=linux_amd64;; *) echo "arch $ARCH?"; exit 1;; esac
if [ ! -x ./mediamtx ]; then
  VER="${MEDIAMTX_VERSION:-v1.12.3}"
  URL="https://github.com/bluenviron/mediamtx/releases/download/${VER}/mediamtx_${VER}_${A}.tar.gz"
  echo "downloading $URL"; curl -fsSL "$URL" | tar xz mediamtx mediamtx.yml
fi
cat > mediamtx.yml <<'YML'
rtspAddress: :8554
rtmpAddress: :1935
srtAddress: :8890
hlsAddress: :8888
webrtcAddress: :8889
paths:
  all_others:
YML
echo "RTSP server on :8554  ->  publish from the phone to rtsp://$(hostname -I | awk '{print $1}'):8554/line"
echo "test:  ffplay rtsp://127.0.0.1:8554/line   (or)   ffprobe rtsp://127.0.0.1:8554/line"
exec ./mediamtx mediamtx.yml
# --- IP Webcam fallback: rewrap MJPEG to RTSP so VSS can ingest it ---
# ffmpeg -re -i http://<PHONE_IP>:8080/video -c:v libx264 -preset ultrafast -tune zerolatency -g 30 -f rtsp rtsp://127.0.0.1:8554/line
