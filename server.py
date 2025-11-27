#!/usr/bin/env python3
"""
Minimal telemetry visualization prototype backed by the Python standard library.

The server exposes two endpoints:
  GET /           -> interactive HTML page (Prototype 2) rendered with Pyodide + pure Python
  GET /telemetry  -> JSON payload with sample telemetry used by the chart
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List


def build_sample_data() -> List[Dict[str, object]]:
    """Generate a small synthetic trip with 1-minute resolution."""
    start = datetime(2024, 5, 1, 9, 0, 0)
    speeds = [0, 5, 20, 35, 50, 65, 80, 75, 60, 45, 30, 15, 0]
    energy = [0.0]
    autopilot = []

    for idx in range(1, len(speeds)):
        delta_kwh = max(speeds[idx], 1) * 0.002  # crude approximation
        energy.append(round(energy[-1] + delta_kwh, 3))

    for idx, speed in enumerate(speeds):
        autopilot.append(speed >= 40 and idx % 2 == 0)

    points = []
    for idx, speed in enumerate(speeds):
        points.append(
            {
                "timestamp": (start + timedelta(minutes=idx)).isoformat(),
                "speed_kmh": speed,
                "autopilot": autopilot[idx],
                "energy_kwh_used": energy[idx],
            }
        )

    return points


SAMPLE_PAYLOAD = {"vehicle": "Prototype AV-1", "trip_id": "demo-trip-001", "points": build_sample_data()}


class TelemetryHandler(BaseHTTPRequestHandler):
    server_version = "TelemetryServer/0.1"

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
        if self.path in ("/", "/index.html"):
            self._serve_index()
        elif self.path == "/telemetry":
            self._serve_json(SAMPLE_PAYLOAD)
        else:
            self._serve_not_found()

    def log_message(self, format: str, *args) -> None:  # noqa: A003 (shadow built-in)
        """Use stdio logging so container orchestrators can capture it."""
        super().log_message(format, *args)

    def _serve_index(self) -> None:
        body = INDEX_HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_not_found(self) -> None:
        body = b"Not Found"
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Telemetry Visualization Prototype 2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light dark;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background-color: #050811;
        color: #f5f5f5;
      }
      body {
        margin: 0;
        padding: 1.5rem;
        background: radial-gradient(circle at top, rgba(12, 28, 54, 0.9), #050811 70%);
        min-height: 100vh;
      }
      .card {
        max-width: 1024px;
        margin: 0 auto;
        padding: 1.5rem;
        background: rgba(8, 13, 24, 0.88);
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      h1 {
        margin-top: 0;
        font-size: clamp(1.5rem, 2.5vw, 2.5rem);
      }
      .subhead {
        margin: 0 0 1rem 0;
        color: #b5bfd7;
      }
      .chart {
        min-height: 420px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
      }
      .chart p {
        margin: 0;
        color: #cfd6ec;
      }
      .status {
        margin-top: 1rem;
        font-size: 0.9rem;
        color: #9fb2d9;
      }
      .error {
        color: #ff6b6b;
      }
      footer {
        margin-top: 1.5rem;
        font-size: 0.85rem;
        opacity: 0.8;
      }
    </style>
    <script src="https://cdn.jsdelivr.net/pyodide/v0.24.1/full/pyodide.js"></script>
  </head>
  <body>
    <div class="card">
      <h1>Vehicle Telemetry (Prototype 2 – Pyodide)</h1>
      <p id="meta" class="subhead">Loading trip details…</p>
      <div id="chart" class="chart" role="img" aria-label="Vehicle telemetry visualization">
        <p>Loading telemetry via Python (WebAssembly)…</p>
      </div>
      <p id="status" class="status">Initializing runtime…</p>
      <footer>
        Prototype 2 renders the visualization using pure Python executed inside the browser with WebAssembly (Pyodide).
      </footer>
    </div>
    <script>
      async function bootstrap() {
        const statusEl = document.getElementById('status');
        try {
          statusEl.textContent = 'Downloading Pyodide runtime…';
          const pyodide = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.24.1/full/' });

          statusEl.textContent = 'Fetching telemetry payload…';
          const res = await fetch('/telemetry');
          if (!res.ok) {
            throw new Error('Failed to fetch telemetry data');
          }
          const payload = await res.json();
          const vehicle = payload.vehicle || 'Vehicle';
          const trip = payload.trip_id || 'Trip';
          document.getElementById('meta').textContent = vehicle + ' · ' + trip;

          pyodide.globals.set('payload_json', JSON.stringify(payload));
          await pyodide.runPythonAsync(`
import json
from datetime import datetime
from js import document

payload = json.loads(payload_json)
points = payload.get("points", [])
chart_el = document.getElementById("chart")

if not points:
    chart_el.innerHTML = "<p>No telemetry samples available.</p>"
else:
    width = 960
    height = 420
    pad = 60
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad

    speed_vals = [p["speed_kmh"] for p in points]
    energy_vals = [p["energy_kwh_used"] for p in points]
    auto_vals = [bool(p["autopilot"]) for p in points]

    speed_max = max(max(speed_vals), 1)
    energy_max = max(max(energy_vals), 1)

    def x_pos(idx: int) -> float:
        if len(points) == 1:
            return pad
        step = inner_w / (len(points) - 1)
        return pad + idx * step

    def y_speed(val: float) -> float:
        return pad + inner_h - (val / speed_max) * inner_h

    def y_energy(val: float) -> float:
        return pad + inner_h - (val / energy_max) * inner_h

    def path(values, fn):
        coords = [f"{x_pos(i):.2f},{fn(v):.2f}" for i, v in enumerate(values)]
        return " ".join(coords)

    speed_path = path(speed_vals, y_speed)
    energy_path = path(energy_vals, y_energy)

    bands = []
    start = None
    for idx, engaged in enumerate(auto_vals):
        if engaged and start is None:
            start = idx
        elif not engaged and start is not None:
            bands.append((start, idx - 1))
            start = None
    if start is not None:
        bands.append((start, len(points) - 1))

    band_rects = []
    for start_idx, end_idx in bands:
        x1 = x_pos(start_idx)
        x2 = x_pos(end_idx)
        width_band = max(x2 - x1, 4)
        band_rects.append(
            f'<rect x="{x1:.2f}" y="{pad - 20}" width="{width_band:.2f}" height="{inner_h + 20}" class="autopilot"></rect>'
        )

    tick_indices = {0, len(points) - 1}
    if len(points) > 2:
        tick_indices.add(len(points) // 2)
    x_ticks = []
    for idx in sorted(tick_indices):
        label_time = datetime.fromisoformat(points[idx]["timestamp"]).strftime("%H:%M")
        x_ticks.append(
            f'<text x="{x_pos(idx):.2f}" y="{pad + inner_h + 30}" class="tick">{label_time}</text>'
        )

    svg = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-label="Speed, energy, and autopilot telemetry">',
        '<defs><style><![CDATA[',
        '.axis { stroke: rgba(255,255,255,0.25); stroke-width: 1; }',
        '.speed { fill: none; stroke: #42b0ff; stroke-width: 3; }',
        '.energy { fill: none; stroke: #ff8f3f; stroke-width: 3; stroke-dasharray: 6 4; }',
        '.autopilot { fill: rgba(0,214,143,0.12); stroke: rgba(0,214,143,0.4); stroke-width: 1; }',
        '.tick { fill: #d4d8e3; font-size: 0.85rem; text-anchor: middle; }',
        '.label { fill: #d4d8e3; font-size: 0.9rem; }',
        ']]></style></defs>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{pad + inner_h}" class="axis"></line>',
        f'<line x1="{pad}" y1="{pad + inner_h}" x2="{pad + inner_w}" y2="{pad + inner_h}" class="axis"></line>',
        *band_rects,
        f'<polyline points="{speed_path}" class="speed"></polyline>',
        f'<polyline points="{energy_path}" class="energy"></polyline>',
        *x_ticks,
        f'<text x="{pad}" y="{pad - 25}" class="label">Speed (km/h)</text>',
        f'<text x="{pad + inner_w}" y="{pad - 25}" class="label" text-anchor="end">Energy (kWh)</text>',
        '</svg>',
    ]
    chart_el.innerHTML = "".join(svg)

del payload_json
`)
          statusEl.textContent = 'Rendered with Pyodide (Prototype 2)';
        } catch (error) {
          console.error(error);
          statusEl.textContent = 'Unable to render telemetry: ' + error.message;
          document.getElementById('chart').innerHTML = '<p class="error">' + error.message + '</p>';
        }
      }

      bootstrap();
    </script>
  </body>
</html>
"""


def run() -> None:
    host = os.environ.get("TELEMETRY_HOST", "127.0.0.1")
    port = int(os.environ.get("TELEMETRY_PORT", "7777"))
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TelemetryHandler)
    print(f"Serving telemetry prototype on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
