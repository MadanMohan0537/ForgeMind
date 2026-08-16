#!/usr/bin/env python3
"""
A stand-in for P2's Core service. This is NOT the real Core - it's here so
you (P1) can prove your events actually make it somewhere sensible and look
correct, without being blocked on P2's implementation. When the real Core
exists, just point pipeline.yaml's core.events_url at it - nothing in
perception/*.py needs to change, since it only ever knows "POST JSON to a URL".

Run: python core_mock/app.py
Dashboard: http://127.0.0.1:5001/dashboard
"""
from flask import Flask, request, jsonify, Response
import time
import threading

app = Flask(__name__)
_lock = threading.Lock()
_events = []          # append-only log of everything received
_zone_state = {}       # zone_name -> latest known state, for the dashboard


@app.route("/events", methods=["POST"])
def receive_event():
    event = request.get_json(force=True)
    with _lock:
        _events.append(event)
        zone = event.get("zone", "unknown")
        _zone_state[zone] = event
    return jsonify({"status": "received"}), 200


@app.route("/events", methods=["GET"])
def list_events():
    with _lock:
        return jsonify(_events[-200:])  # last 200, oldest-first within that window


@app.route("/dashboard")
def dashboard():
    with _lock:
        zones_html = ""
        for zone, event in sorted(_zone_state.items()):
            payload = event.get("payload", {})
            zones_html += f"""
            <div class="card">
              <h3>{zone}</h3>
              <div class="type">{event.get('type', '?')}</div>
              <div class="ts">{time.strftime('%H:%M:%S', time.localtime(event.get('timestamp', 0)))}</div>
              <pre>{payload}</pre>
            </div>
            """
        recent = "".join(
            f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(e.get('timestamp',0)))}</td>"
            f"<td>{e.get('type')}</td><td>{e.get('zone')}</td>"
            f"<td><code>{e.get('payload')}</code></td></tr>"
            for e in reversed(_events[-30:])
        )

    return Response(f"""
    <html>
    <head>
      <meta http-equiv="refresh" content="2">
      <style>
        body {{ font-family: sans-serif; background: #111; color: #eee; padding: 20px; }}
        .cards {{ display: flex; gap: 16px; flex-wrap: wrap; }}
        .card {{ background: #1e1e1e; border-radius: 8px; padding: 16px; min-width: 220px; }}
        .card h3 {{ margin: 0 0 8px; }}
        .type {{ color: #6cf; font-weight: bold; }}
        .ts {{ color: #888; font-size: 12px; margin-bottom: 8px; }}
        pre {{ background: #000; padding: 8px; border-radius: 4px; font-size: 12px; }}
        table {{ width: 100%; margin-top: 24px; border-collapse: collapse; }}
        td, th {{ border-bottom: 1px solid #333; padding: 6px 10px; text-align: left; font-size: 13px; }}
      </style>
    </head>
    <body>
      <h2>Core (mock) — zone state</h2>
      <div class="cards">{zones_html or '<p>No events yet.</p>'}</div>
      <h2>Recent events</h2>
      <table><tr><th>time</th><th>type</th><th>zone</th><th>payload</th></tr>{recent}</table>
    </body>
    </html>
    """, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
