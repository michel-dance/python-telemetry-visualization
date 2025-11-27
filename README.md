# python-telemetry-visualization
Prototype web based vehicle telemetry visualization using python

## Value statement

As a data analytics researcher for the vehicle driving automation domain, I would like to visualize vehicle telemetry data on my research laptop, and also be able to share the visualizations with others.

## Architectural considersations

Given that with the onset of artificial intelligence(AI) based software development, we want to create a solution that is a easy as possible for AI to maintain. The architecture of this application should be as simple as possible, and include the least amount of third party dependencies. 

We are going to go out on a limb and assume that Python is going to be the de facto standard language for LLM execute compute on, so LLMs will be best equiped to maintain the Python langage based applications.

As Linux is the foundation of server side compute, we will also assume that future development environment will be mostly Linux based, so the application shall be a Linux first and only solution. 

## Domain 

The domain is vehicle driving automation.

As a vehicle fleet manager, I would like to review the telemetry data on my vehicles after a vehicle has completed a trip.

The vehicle telemetry includes speed, gps, auto pilot, and energy usage data.

## Prototype

A web based appliction that shows a sample vehicle telemetry visualiztion for an hypothetical trip.

## Prototype 1 implementation

The initial version provides a single-file Python backend (`server.py`) plus a static HTML page that used Chart.js to render speed, energy usage, and autopilot data. Prototype 1 proved out the data model and API surface but still relied on a JavaScript charting library for visualization.

![Demo screenshot](prototype1.png)

## Prototype 2 implementation

Prototype 2 keeps the lightweight Python backend but swaps the front-end charting layer for pure Python executed in the browser via WebAssembly (Pyodide). The Pyodide runtime pulls `/telemetry`, processes the JSON, and emits an inline SVG that plots:

- Speed (km/h) on the left axis
- Cumulative energy (kWh) on the right axis
- Autopilot engagement bands across the plot background

This keeps the visualization logic in Python, avoiding the need to maintain JavaScript charting code going forward. The HTML still loads Pyodide from a CDN, so a network connection is required the first time the page loads to download the runtime (~8 MB).

![Demo screenshot](prototype2.png)

### Prerequisites

- Python 3.9 or newer (only the Python standard library is required).

### Getting started

```bash
python3 server.py
```

Then open your browser to [http://127.0.0.1:7777](http://127.0.0.1:7777). The Pyodide runtime download happens in the browser; subsequent loads are served from cache.

Environment variables:

- `TELEMETRY_HOST` – host/interface to bind to (default `127.0.0.1`)
- `TELEMETRY_PORT` – port to listen on (default `7777`)

Kill the server with `Ctrl+C`. The `/telemetry` endpoint can also be queried directly to inspect the sample JSON payload.

