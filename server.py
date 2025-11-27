#!/usr/bin/env python3
"""
Minimal telemetry visualization prototype backed by the Python standard library.

The server exposes two endpoints:
  GET /           -> interactive HTML page with a Chart.js visualization
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
    <title>Telemetry Visualization Prototype</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light dark;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background-color: #0b1526;
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
        background: rgba(8, 13, 24, 0.85);
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      h1 {
        margin-top: 0;
        font-size: clamp(1.5rem, 2.5vw, 2.5rem);
      }
      canvas {
        width: 100%;
        max-height: 480px;
      }
      .legend {
        margin-top: 1rem;
        font-size: 0.95rem;
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
      }
      .chip {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
      }
      .chip span {
        width: 12px;
        height: 12px;
        border-radius: 999px;
        display: inline-block;
      }
      .chip .speed {
        background: #42b0ff;
      }
      .chip .energy {
        background: #ff8f3f;
      }
      .chip .autopilot {
        background: #00d68f;
      }
      footer {
        margin-top: 1.5rem;
        font-size: 0.85rem;
        opacity: 0.8;
      }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  </head>
  <body>
    <div class="card">
      <h1>Vehicle Telemetry (Prototype)</h1>
      <canvas id="telemetryChart" aria-label="Trip telemetry visualization"></canvas>
      <div class="legend" aria-hidden="true">
        <div class="chip"><span class="speed"></span>Speed</div>
        <div class="chip"><span class="energy"></span>Cumulative Energy Used</div>
        <div class="chip"><span class="autopilot"></span>Autopilot Active</div>
      </div>
      <footer>
        Sample trip: speed in km/h, energy in kWh used, autopilot indicator.
      </footer>
    </div>
    <script>
      async function initChart() {
        const res = await fetch('/telemetry');
        if (!res.ok) {
          throw new Error('Failed to load telemetry data');
        }
        const payload = await res.json();
        const labels = payload.points.map(p => new Date(p.timestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}));
        const autopilot = payload.points.map(p => p.autopilot ? 1 : 0);
        const speed = payload.points.map(p => p.speed_kmh);
        const energy = payload.points.map(p => p.energy_kwh_used);
        const ctx = document.getElementById('telemetryChart');
        new Chart(ctx, {
          type: 'line',
          data: {
            labels,
            datasets: [
              {
                label: 'Speed (km/h)',
                data: speed,
                borderColor: '#42b0ff',
                backgroundColor: 'rgba(66, 176, 255, 0.15)',
                tension: 0.3,
                yAxisID: 'y',
                fill: true,
              },
              {
                label: 'Cumulative Energy (kWh)',
                data: energy,
                borderColor: '#ff8f3f',
                backgroundColor: 'rgba(255, 143, 63, 0.2)',
                tension: 0.4,
                yAxisID: 'y1',
              },
              {
                label: 'Autopilot Active',
                data: autopilot,
                borderColor: '#00d68f',
                backgroundColor: 'rgba(0, 214, 143, 0.3)',
                stepped: true,
                yAxisID: 'y2',
              },
            ],
          },
          options: {
            responsive: true,
            interaction: {
              mode: 'index',
              intersect: false,
            },
            stacked: false,
            plugins: {
              legend: {
                labels: {
                  color: '#f5f5f5',
                },
              },
              tooltip: {
                callbacks: {
                  afterBody(items) {
                    const idx = items[0].dataIndex;
                    const point = payload.points[idx];
                    return `Autopilot: ${point.autopilot ? 'engaged' : 'manual'}`;
                  },
                },
              },
            },
            scales: {
              x: {
                ticks: { color: '#d4d8e3' },
                grid: { color: 'rgba(255,255,255,0.05)' },
              },
              y: {
                type: 'linear',
                position: 'left',
                title: { display: true, text: 'Speed (km/h)' },
                ticks: { color: '#d4d8e3' },
                grid: { color: 'rgba(255,255,255,0.05)' },
              },
              y1: {
                type: 'linear',
                position: 'right',
                title: { display: true, text: 'Energy (kWh)' },
                ticks: { color: '#d4d8e3' },
                grid: { drawOnChartArea: false },
              },
              y2: {
                type: 'linear',
                position: 'right',
                display: false,
                min: 0,
                max: 1,
              },
            },
          },
        });
      }

      initChart().catch((err) => {
        document.querySelector('.card').insertAdjacentHTML(
          'beforeend',
          `<p style="color:#ff6b6b">Unable to load telemetry data: ${err.message}</p>`
        );
      });
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
