#!/usr/bin/env python3
"""
Minimal telemetry visualization prototype backed by the Python standard library.

The server exposes three endpoints:
  GET /                 -> interactive HTML page with an embedded SVG chart
  GET /telemetry        -> JSON payload with sample telemetry used by the chart
  GET /visualization.svg -> raw SVG image of the telemetry visualization (downloadable)
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


def build_visualization_svg(payload: Dict[str, object]) -> str:
    """Render the telemetry payload into an SVG polyline chart."""
    points = payload.get("points", [])
    width = 960
    height = 420
    pad = 60
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad

    if not points:
        return (
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            'aria-label="Empty telemetry visualization">'
            '<rect width="100%" height="100%" fill="#050811"></rect>'
            '<text x="50%" y="50%" fill="#d4d8e3" font-size="20" text-anchor="middle">No data</text>'
            "</svg>"
        )

    speed_vals = [float(p["speed_kmh"]) for p in points]
    energy_vals = [float(p["energy_kwh_used"]) for p in points]
    autopilot_vals = [bool(p["autopilot"]) for p in points]

    speed_max = max(max(speed_vals), 1.0)
    energy_max = max(max(energy_vals), 1.0)

    def x_pos(idx: int) -> float:
        if len(points) == 1:
            return pad
        step = inner_w / (len(points) - 1)
        return pad + idx * step

    def y_speed(value: float) -> float:
        return pad + inner_h - (value / speed_max) * inner_h

    def y_energy(value: float) -> float:
        return pad + inner_h - (value / energy_max) * inner_h

    def build_polyline(values: List[float], mapper) -> str:
        coords = [f"{x_pos(idx):.2f},{mapper(val):.2f}" for idx, val in enumerate(values)]
        return " ".join(coords)

    speed_path = build_polyline(speed_vals, y_speed)
    energy_path = build_polyline(energy_vals, y_energy)

    bands = []
    start_idx = None
    for idx, engaged in enumerate(autopilot_vals):
        if engaged and start_idx is None:
            start_idx = idx
        elif not engaged and start_idx is not None:
            bands.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        bands.append((start_idx, len(points) - 1))

    band_rects = []
    for start, end in bands:
        x1 = x_pos(start)
        x2 = x_pos(end)
        width_band = max(x2 - x1, 4)
        band_rects.append(
            f'<rect x="{x1:.2f}" y="{pad - 20}" width="{width_band:.2f}" '
            f'height="{inner_h + 20:.2f}" class="autopilot"></rect>'
        )

    tick_indices = {0, len(points) - 1}
    if len(points) > 2:
        tick_indices.add(len(points) // 2)
    tick_labels = []
    for idx in sorted(tick_indices):
        ts = datetime.fromisoformat(str(points[idx]["timestamp"]))
        label = ts.strftime("%H:%M")
        tick_labels.append(
            f'<text x="{x_pos(idx):.2f}" y="{pad + inner_h + 30}" class="tick">{label}</text>'
        )

    svg_parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Speed, energy, autopilot telemetry">',
        '<defs><style><![CDATA[',
        '.bg { fill: #050811; }',
        '.axis { stroke: rgba(255,255,255,0.25); stroke-width: 1; }',
        '.speed { fill: none; stroke: #42b0ff; stroke-width: 3; }',
        '.energy { fill: none; stroke: #ff8f3f; stroke-width: 3; stroke-dasharray: 6 4; }',
        '.autopilot { fill: rgba(0,214,143,0.12); stroke: rgba(0,214,143,0.4); stroke-width: 1; }',
        '.tick { fill: #d4d8e3; font-size: 0.85rem; text-anchor: middle; }',
        '.label { fill: #d4d8e3; font-size: 0.9rem; }',
        ']]></style></defs>',
        f'<rect width="{width}" height="{height}" class="bg"></rect>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{pad + inner_h:.2f}" class="axis"></line>',
        f'<line x1="{pad}" y1="{pad + inner_h:.2f}" x2="{pad + inner_w:.2f}" y2="{pad + inner_h:.2f}" class="axis"></line>',
        *band_rects,
        f'<polyline points="{speed_path}" class="speed"></polyline>',
        f'<polyline points="{energy_path}" class="energy"></polyline>',
        *tick_labels,
        f'<text x="{pad}" y="{pad - 25}" class="label">Speed (km/h)</text>',
        f'<text x="{pad + inner_w}" y="{pad - 25}" class="label" text-anchor="end">Energy (kWh)</text>',
        '</svg>',
    ]
    return "".join(svg_parts)


def build_index_html(payload: Dict[str, object]) -> str:
    """Return the complete HTML page with the embedded SVG visualization."""
    svg_markup = build_visualization_svg(payload)
    vehicle = payload.get("vehicle", "Vehicle")
    trip = payload.get("trip_id", "Trip")
    meta = f"{vehicle} · {trip}"

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Telemetry Visualization Prototype 2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        color-scheme: light dark;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background-color: #050811;
        color: #f5f5f5;
      }}
      body {{
        margin: 0;
        padding: 1.5rem;
        background: radial-gradient(circle at top, rgba(12, 28, 54, 0.9), #050811 70%);
        min-height: 100vh;
      }}
      .card {{
        max-width: 1024px;
        margin: 0 auto;
        padding: 1.5rem;
        background: rgba(8, 13, 24, 0.88);
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
      }}
      h1 {{
        margin-top: 0;
        font-size: clamp(1.5rem, 2.5vw, 2.5rem);
      }}
      .subhead {{
        margin: 0 0 1rem 0;
        color: #b5bfd7;
      }}
      .chart {{
        min-height: 420px;
      }}
      .legend {{
        margin-top: 1rem;
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        font-size: 0.95rem;
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
      }}
      .chip span {{
        width: 12px;
        height: 12px;
        border-radius: 999px;
        display: inline-block;
      }}
      .chip .speed {{ background: #42b0ff; }}
      .chip .energy {{ background: #ff8f3f; }}
      .chip .autopilot {{ background: #00d68f; }}
      .actions {{
        margin-top: 1.5rem;
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
      }}
      .button {{
        padding: 0.65rem 1.2rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        color: inherit;
        text-decoration: none;
      }}
      footer {{
        margin-top: 1rem;
        font-size: 0.85rem;
        opacity: 0.8;
      }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Vehicle Telemetry (Prototype 2 – Server SVG)</h1>
      <p class="subhead">{meta}</p>
      <div class="chart" role="img" aria-label="Vehicle telemetry visualization">
        {svg_markup}
      </div>
      <div class="legend" aria-hidden="true">
        <div class="chip"><span class="speed"></span>Speed</div>
        <div class="chip"><span class="energy"></span>Cumulative Energy</div>
        <div class="chip"><span class="autopilot"></span>Autopilot Engaged</div>
      </div>
      <div class="actions">
        <a class="button" href="/visualization.svg" download="telemetry.svg">Download SVG</a>
        <a class="button" href="/telemetry" target="_blank" rel="noopener">View JSON</a>
      </div>
      <footer>
        Visualization generated on the server to keep the prototype Python-first and easy to maintain.
      </footer>
    </div>
  </body>
</html>
"""
class TelemetryHandler(BaseHTTPRequestHandler):
    server_version = "TelemetryServer/0.1"

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
        if self.path in ("/", "/index.html"):
            self._serve_index()
        elif self.path == "/telemetry":
            self._serve_json(SAMPLE_PAYLOAD)
        elif self.path == "/visualization.svg":
            self._serve_svg(SAMPLE_PAYLOAD)
        else:
            self._serve_not_found()

    def log_message(self, format: str, *args) -> None:  # noqa: A003 (shadow built-in)
        """Use stdio logging so container orchestrators can capture it."""
        super().log_message(format, *args)

    def _serve_index(self) -> None:
        body = build_index_html(SAMPLE_PAYLOAD).encode("utf-8")
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

    def _serve_svg(self, payload: Dict[str, object]) -> None:
        body = build_visualization_svg(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)




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
