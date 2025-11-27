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

## Prototype implementation

This repository contains a single-file Python prototype (`server.py`) that serves a static HTML page and a JSON endpoint with synthetic telemetry. The page visualizes speed, cumulative energy usage, and autopilot engagement through a multi-axis chart rendered with Chart.js (loaded from a CDN to avoid Python dependencies).

![Demo screenshot](demo1.png)



### Prerequisites

- Python 3.9 or newer (only the Python standard library is required).

### Getting started

```bash
python3 server.py
```

Then open your browser to [http://127.0.0.1:7777](http://127.0.0.1:7777).

Environment variables:

- `TELEMETRY_HOST` – host/interface to bind to (default `127.0.0.1`)
- `TELEMETRY_PORT` – port to listen on (default `7777`)

Kill the server with `Ctrl+C`. The `/telemetry` endpoint can also be queried directly to inspect the sample JSON payload.


