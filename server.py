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
from urllib.parse import parse_qs, urlparse


def build_sample_data() -> List[Dict[str, object]]:
    """Generate a small synthetic trip with 1-minute resolution."""
    start = datetime(2024, 5, 1, 9, 0, 0)
    speeds = [0, 5, 20, 35, 50, 65, 80, 75, 60, 45, 30, 15, 0]
    energy = [0.0]
    autopilot = []
    throttle = [0, 15, 45, 60, 78, 88, 95, 80, 55, 30, 10, 0, 0]
    brake = [80, 40, 10, 5, 0, 0, 0, 0, 10, 25, 45, 70, 90]

    for idx in range(1, len(speeds)):
        delta_kwh = max(speeds[idx], 1) * 0.002  # crude approximation
        energy.append(round(energy[-1] + delta_kwh, 3))

    # Craft autopilot bands with varying lengths so the engagement bar shows
    # distinct segments rather than a repeating on/off cadence.
    autopilot_segments = [(1, 3), (5, 9), (11, 12)]
    engaged_lookup = [False] * len(speeds)
    for start, end in autopilot_segments:
        for idx in range(start, min(end + 1, len(engaged_lookup))):
            engaged_lookup[idx] = True

    for idx, _ in enumerate(speeds):
        autopilot.append(engaged_lookup[idx])

    points = []
    for idx, speed in enumerate(speeds):
        points.append(
            {
                "timestamp": (start + timedelta(minutes=idx)).isoformat(),
                "speed_kmh": speed,
                "autopilot": autopilot[idx],
                "energy_kwh_used": energy[idx],
                "throttle_pct": throttle[idx],
                "brake_pct": brake[idx],
            }
        )

    return points


SAMPLE_PAYLOAD = {"vehicle": "Prototype AV-1", "trip_id": "demo-trip-001", "points": build_sample_data()}


def resolve_playback_index(points: List[Dict[str, object]], query: Dict[str, List[str]]) -> int:
    """Determine which telemetry sample should define time t."""
    total = len(points)
    if total == 0:
        return 0

    def clamp(idx: int) -> int:
        return max(0, min(idx, total - 1))

    if query:
        idx_values = query.get("idx")
        if idx_values:
            try:
                return clamp(int(idx_values[0]))
            except (TypeError, ValueError):
                pass

        for key in ("t", "time", "timestamp"):
            ts_values = query.get(key)
            if not ts_values:
                continue
            try:
                target = datetime.fromisoformat(ts_values[0])
            except ValueError:
                continue

            best_idx = 0
            best_delta = float("inf")
            for idx, point in enumerate(points):
                ts = datetime.fromisoformat(str(point["timestamp"]))
                delta = abs((ts - target).total_seconds())
                if delta < best_delta:
                    best_delta = delta
                    best_idx = idx
            return best_idx

    return total // 2


def build_visualization_svg(payload: Dict[str, object], playback_idx: int | None = None) -> str:
    """Render the telemetry payload into a stacked SVG visualization."""
    points = payload.get("points", [])
    width = 960
    pad_left = 60
    pad_right = 60
    pad_top = 40
    pad_bottom = 65
    group2_height = 240  # Speed + Energy (top)
    group_gap = 40
    group1_control_height = 110
    autopilot_bar_height = 45
    autopilot_gap = 40
    group1_height = group1_control_height + autopilot_gap + autopilot_bar_height
    inner_w = width - pad_left - pad_right
    height = pad_top + group2_height + group_gap + group1_height + pad_bottom

    if not points:
        return (
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            'aria-label="Empty telemetry visualization">'
            '<rect width="100%" height="100%" fill="#050811"></rect>'
            '<text x="50%" y="50%" fill="#d4d8e3" font-size="20" text-anchor="middle">No data</text>'
            "</svg>"
        )

    if playback_idx is None:
        playback_idx = len(points) // 2
    playback_idx = max(0, min(playback_idx, len(points) - 1))

    group2_top = pad_top
    group2_bottom = group2_top + group2_height
    group1_top = group2_bottom + group_gap
    group1_bottom = group1_top + group1_height
    control_top = group1_top
    control_bottom = control_top + group1_control_height
    autopilot_top = control_bottom + autopilot_gap
    autopilot_bottom = autopilot_top + autopilot_bar_height

    speed_vals = [float(p["speed_kmh"]) for p in points]
    energy_vals = [float(p["energy_kwh_used"]) for p in points]
    throttle_vals = [float(p.get("throttle_pct", 0.0)) for p in points]
    brake_vals = [float(p.get("brake_pct", 0.0)) for p in points]
    autopilot_vals = [bool(p["autopilot"]) for p in points]

    speed_max = max(max(speed_vals), 1.0)
    energy_max = max(max(energy_vals), 1.0)

    def x_pos(idx: int) -> float:
        if len(points) == 1:
            return pad_left
        step = inner_w / (len(points) - 1)
        return pad_left + idx * step

    def y_speed(value: float) -> float:
        return group2_bottom - (value / speed_max) * group2_height

    def y_energy(value: float) -> float:
        return group2_bottom - (value / energy_max) * group2_height

    def y_throttle(value: float) -> float:
        return control_bottom - (value / 100.0) * group1_control_height

    def y_brake(value: float) -> float:
        return control_bottom - (value / 100.0) * group1_control_height

    def build_polyline(values: List[float], mapper) -> str:
        coords = [f"{x_pos(idx):.2f},{mapper(val):.2f}" for idx, val in enumerate(values)]
        return " ".join(coords)

    playback_x = x_pos(playback_idx)

    speed_path = build_polyline(speed_vals, y_speed)
    energy_path = build_polyline(energy_vals, y_energy)
    throttle_path = build_polyline(throttle_vals, y_throttle)
    brake_path = build_polyline(brake_vals, y_brake)

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

    autopilot_rects = []
    for start, end in bands:
        x1 = x_pos(start)
        x2 = x_pos(end)
        width_band = max(x2 - x1, 4)
        autopilot_rects.append(
            f'<rect x="{x1:.2f}" y="{autopilot_top:.2f}" width="{width_band:.2f}" '
            f'height="{autopilot_bar_height:.2f}" class="autopilot"></rect>'
        )

    tick_indices = {0, len(points) - 1}
    if len(points) > 2:
        tick_indices.add(len(points) // 2)
    tick_labels = []
    for idx in sorted(tick_indices):
        ts = datetime.fromisoformat(str(points[idx]["timestamp"]))
        label = ts.strftime("%H:%M")
        tick_labels.append(
            f'<text x="{x_pos(idx):.2f}" y="{group1_bottom + 30}" class="tick">{label}</text>'
        )

    svg_parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Telemetry grouped by vehicle dynamics and control states">',
        '<defs><style><![CDATA[',
        '.bg { fill: #050811; }',
        '.axis { stroke: rgba(255,255,255,0.25); stroke-width: 1; }',
        '.divider { stroke: rgba(255,255,255,0.15); stroke-width: 1; stroke-dasharray: 4 4; }',
        '.speed { fill: none; stroke: #42b0ff; stroke-width: 3; }',
        '.energy { fill: none; stroke: #ff8f3f; stroke-width: 3; stroke-dasharray: 6 4; }',
        '.throttle { fill: none; stroke: #f2cf63; stroke-width: 2.5; }',
        '.brake { fill: none; stroke: #ff5c93; stroke-width: 2.5; stroke-dasharray: 5 4; }',
        '.autopilot { fill: rgba(0,214,143,0.12); stroke: rgba(0,214,143,0.4); stroke-width: 1; }',
        '.tick { fill: #d4d8e3; font-size: 0.85rem; text-anchor: middle; }',
        '.label { fill: #d4d8e3; font-size: 0.9rem; }',
        '.group-label { fill: #b5bfd7; font-size: 0.9rem; }',
        '.playback { stroke: rgba(255, 255, 255, 0.7); stroke-width: 2; stroke-dasharray: 10 8; }',
        ']]></style></defs>',
        f'<rect width="{width}" height="{height}" class="bg"></rect>',
        f'<text x="{pad_left}" y="{group2_top - 12}" class="group-label">Group 2 · Speed &amp; Energy</text>',
        f'<text x="{pad_left}" y="{group1_top - 12}" class="group-label">Group 1 · Control Inputs</text>',
        f'<line x1="{pad_left}" y1="{group2_top}" x2="{pad_left}" y2="{group2_bottom}" class="axis"></line>',
        f'<line x1="{pad_left}" y1="{group2_bottom}" x2="{pad_left + inner_w}" y2="{group2_bottom}" class="axis"></line>',
        f'<line x1="{pad_left}" y1="{group1_top}" x2="{pad_left + inner_w}" y2="{group1_top}" class="divider"></line>',
        f'<line x1="{pad_left}" y1="{control_bottom}" x2="{pad_left + inner_w}" y2="{control_bottom}" class="divider"></line>',
        f'<line x1="{pad_left}" y1="{group1_bottom}" x2="{pad_left + inner_w}" y2="{group1_bottom}" class="axis"></line>',
        f'<line x1="{playback_x:.2f}" y1="{group2_top}" x2="{playback_x:.2f}" y2="{group1_bottom}" class="playback"></line>',
        *autopilot_rects,
        f'<polyline points="{speed_path}" class="speed"></polyline>',
        f'<polyline points="{energy_path}" class="energy"></polyline>',
        f'<polyline points="{throttle_path}" class="throttle"></polyline>',
        f'<polyline points="{brake_path}" class="brake"></polyline>',
        *tick_labels,
        f'<text x="{pad_left}" y="{group2_top - 30}" class="label">Speed (km/h)</text>',
        f'<text x="{pad_left + inner_w}" y="{group2_top - 30}" class="label" text-anchor="end">Energy (kWh)</text>',
        f'<text x="{pad_left}" y="{control_top + 20}" class="label">Throttle / Brake (%)</text>',
        f'<text x="{pad_left}" y="{autopilot_top + autopilot_bar_height / 2:.2f}" class="label" dominant-baseline="middle">Autopilot engagement</text>',
        f'<text x="{pad_left + inner_w}" y="{group1_bottom + 50}" class="label" text-anchor="end">Time</text>',
        '</svg>',
    ]
    return "".join(svg_parts)


def build_index_html(payload: Dict[str, object], playback_idx: int | None = None) -> str:
    """Return the complete HTML page with the embedded SVG visualization."""
    points: List[Dict[str, object]] = payload.get("points", [])
    total_points = len(points)
    if total_points == 0:
        playback_idx = 0
    elif playback_idx is None:
        playback_idx = total_points // 2
    playback_idx = max(0, min(playback_idx, max(total_points - 1, 0)))

    svg_markup = build_visualization_svg(payload, playback_idx)
    vehicle = payload.get("vehicle", "Vehicle")
    trip = payload.get("trip_id", "Trip")
    meta = f"{vehicle} · {trip}"

    playback_point = points[playback_idx] if points else {}
    if playback_point:
        playback_ts = datetime.fromisoformat(str(playback_point["timestamp"]))
        playback_label = playback_ts.strftime("%Y-%m-%d %H:%M")
    else:
        playback_label = "—"
    table_rows = [
        ("Time", playback_label),
        (
            "Speed (km/h)",
            f"{float(playback_point.get('speed_kmh', 0.0)):.0f}" if playback_point else "—",
        ),
        (
            "Cumulative energy (kWh)",
            f"{float(playback_point.get('energy_kwh_used', 0.0)):.2f}" if playback_point else "—",
        ),
        (
            "Autopilot",
            "Engaged" if playback_point.get("autopilot") else ("Disengaged" if playback_point else "—"),
        ),
        (
            "Throttle position (%)",
            f"{float(playback_point.get('throttle_pct', 0.0)):.0f}" if playback_point else "—",
        ),
        (
            "Brake position (%)",
            f"{float(playback_point.get('brake_pct', 0.0)):.0f}" if playback_point else "—",
        ),
    ]

    table_body = "\n".join(
        f'          <tr><th scope="row">{label}</th><td>{value}</td></tr>' for label, value in table_rows
    )
    table_hint = (
        f"Sample {playback_idx + 1} of {total_points}. "
        "Use ?idx=N or ?time=YYYY-MM-DDTHH:MM to inspect another timestamp."
        if points
        else "Load telemetry to inspect the trip timeline."
    )

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
      .viz-grid {{
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr);
        gap: 1.5rem;
        align-items: flex-start;
      }}
      @media (max-width: 900px) {{
        .viz-grid {{
          grid-template-columns: 1fr;
        }}
      }}
      .chart {{
        min-height: 420px;
        width: 100%;
      }}
      .chart svg {{
        width: 100%;
        height: auto;
        display: block;
      }}
      .table-section {{
        padding: 1.25rem;
        background: rgba(15, 23, 44, 0.85);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.08);
      }}
      .table-section h2 {{
        margin: 0 0 0.25rem 0;
        font-size: 1.1rem;
      }}
      .table-meta {{
        margin: 0 0 1rem 0;
        color: #8ca2ce;
        font-size: 0.9rem;
      }}
      .telemetry-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
      }}
      .telemetry-table th {{
        text-align: left;
        padding: 0.35rem 0.75rem 0.35rem 0;
        color: #9fb2d9;
        font-weight: 600;
        white-space: nowrap;
      }}
      .telemetry-table td {{
        padding: 0.35rem 0;
        color: #f5f7ff;
      }}
      .legend {{
        margin-top: 2rem;
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
      .chip .throttle {{ background: #f2cf63; }}
      .chip .brake {{ background: #ff5c93; }}
      .summary {{
        margin: 0 0 1.25rem 0;
        color: #9fb2d9;
        font-size: 0.95rem;
      }}
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
      <p class="summary">Group 2 (speed & energy) sits above Group 1, where throttle and brake traces ride over a dedicated autopilot engagement bar. The telemetry table lives to the right so you can see the current values while keeping the full chart in view.</p>
      <div class="viz-grid">
        <div class="chart" role="img" aria-label="Vehicle telemetry visualization">
          {svg_markup}
        </div>
        <section class="table-section" aria-live="polite">
          <h2>Telemetry at time t</h2>
          <p class="table-meta">{table_hint}</p>
          <table class="telemetry-table">
            <tbody>
{table_body}
            </tbody>
          </table>
        </section>
      </div>
      <div class="legend" aria-hidden="true">
        <div class="chip"><span class="speed"></span>Speed</div>
        <div class="chip"><span class="energy"></span>Cumulative Energy</div>
        <div class="chip"><span class="throttle"></span>Throttle</div>
        <div class="chip"><span class="brake"></span>Brake</div>
        <div class="chip"><span class="autopilot"></span>Autopilot bar</div>
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
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        query = parse_qs(parsed.query)
        playback_idx = resolve_playback_index(SAMPLE_PAYLOAD.get("points", []), query)

        if path in ("/", "/index.html"):
            self._serve_index(playback_idx)
        elif path == "/telemetry":
            self._serve_json(SAMPLE_PAYLOAD)
        elif path == "/visualization.svg":
            self._serve_svg(SAMPLE_PAYLOAD, playback_idx)
        else:
            self._serve_not_found()

    def log_message(self, format: str, *args) -> None:  # noqa: A003 (shadow built-in)
        """Use stdio logging so container orchestrators can capture it."""
        super().log_message(format, *args)

    def _serve_index(self, playback_idx: int) -> None:
        body = build_index_html(SAMPLE_PAYLOAD, playback_idx).encode("utf-8")
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

    def _serve_svg(self, payload: Dict[str, object], playback_idx: int) -> None:
        body = build_visualization_svg(payload, playback_idx).encode("utf-8")
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
