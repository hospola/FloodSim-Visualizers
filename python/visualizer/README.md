# Python Visualizer

A Python MQTT monitor for DanaSim flood simulations, plus a set of offline
tools for turning recorded simulation output into map tiles and 3D
heightmap viewers.

## Components

- **`main.py`** — entry point for the live MQTT monitor (`python -m
  python.visualizer`). Connects to the broker, performs the handshake, and
  dispatches incoming events to `SimulationApp`.
- **`simulation_app.py`** — application core. Owns the simulation grid state
  and the protocol state machine; depends only on the ports below (no MQTT or
  rendering imports).
- **`data_model.py`** — `SimulationGrid`: the in-memory grid (terrain heights +
  flood state per cell) and the logic to apply `InitMap_Config`,
  `InitAgent_Layer` and per-frame `EYE_SetState_Layer` updates.
- **`network.py`** — `MQTTMonitorClient`: the MQTT adapter (paho-mqtt),
  handshake/reconnect logic and topic subscriptions.
- **`ports.py`** — protocol interfaces (`SimulationEventHandler`,
  `ControlPublisher`) connecting the app core to adapters.
- **`demo.py`** — synthetic end-to-end demo, no MQTT broker required.
- **`run_viz.py`** — offline visualization pipeline runner (tiles, X3D, HTTP
  server).

## Renderers

Selected via `renderer.type` in `mqtt.yml` (`RENDERER_TYPE`), registered in
[`renderers/registry.py`](renderers/registry.py):

| Type | Class | Output |
|---|---|---|
| `csv` | [`CSVRenderer`](renderers/csv/csv_renderer.py) | Sparse per-frame CSVs (`csv_data/step_NNNNN.csv`) + `terrain.npy` + `meta.json` — the canonical offline format consumed by the tile/X3D tools |
| `2d` | [`MatplotlibRenderer`](renderers/matplotlib_renderer.py) | PNG snapshots of the grid per frame |
| `x3d` | [`X3DRenderer`](renderers/x3d/x3d_renderer.py) | Live-updating X3D player (`player.html` + per-frame flood PNGs + `manifest.json`) |

## Depth providers

Selected via `renderer.depth_provider` in `mqtt.yml`, registered in the same
registry:

| Type | Class | Behaviour |
|---|---|---|
| `palette` | [`PaletteDepthProvider`](depth_providers/palette.py) | Maps discrete flood-risk levels (0–5) from `EYE_SetState_Layer` to representative depth values using `FLOOD_LEVELS` thresholds |
| `direct` | [`DirectDepthProvider`](depth_providers/direct.py) | Uses water-depth values directly when the simulator provides them |

## Configuration

### `mqtt.yml`

Central config for the live monitor (`config.py`). Key sections:

- `sim_config` — path to the DanaSim simulator's own YAML config (see
  [`../../config/`](../../config/) for samples). Used to derive
  `FLOOD_LEVELS` (risk thresholds) and the dataset name for `file`-mode
  initial state.
- `mqtt` — broker host/port, scenario name (`FloodSim/{scenario}/...`
  topics), QoS, handshake/frame timeouts.
- `renderer` — renderer + depth provider selection, output folder.
- `visualizer.initial_state_source` — `mqtt` (wait for
  `EYE_SetState_Layer`) or `file` (read `water_depth` directly from disk,
  reduces simulator RAM usage).

Every `mqtt.yml` value can be overridden by an environment variable (see
`_get()` in [`config.py`](config.py)), e.g. `DANASIM_MQTT_HOST`,
`DANASIM_SCENARIO`, `DANASIM_RENDERER`.

### `viz.yml`

Config for the offline `run_viz.py` pipeline: input/output paths (IDRISI
terrain, CSV data, tile/X3D output dirs, color palette) and tile zoom levels.

## Running

```bash
# Live monitor (needs an MQTT broker + sim_config)
python -m python.visualizer

# Synthetic demo, no broker needed
python -m python.visualizer.demo --renderer x3d --output ./demo_output

# Offline pipeline (reads viz.yml)
python -m python.visualizer.run_viz terrain   # IDRISI -> terrain tile pyramid + georef.json
python -m python.visualizer.run_viz flood     # csv_data/ + georef.json -> flood tile pyramid
python -m python.visualizer.run_viz x3d       # csv_data/ -> X3D heightmap player
python -m python.visualizer.run_viz all       # terrain + flood + x3d
python -m python.visualizer.run_viz serve     # serve outputs/ over HTTP
```

## Tools

- **[`tools/x3d_player/`](tools/x3d_player/)** — generates a self-contained
  X3D/X_ITE HTML player (flat or tiled/LOD) from `csv_data/`. Used by both
  `X3DRenderer` (live) and `run_viz x3d` (offline,
  `tools/generate_x3d_heightmap.py` is a backwards-compatible shim).
- **[`tools/generate_x3d.py`](tools/generate_x3d.py)** — older standalone X3D
  generator (flat or tiled LOD output).
- **[`tools/generate_terrain_tiles.py`](tools/generate_terrain_tiles.py)** /
  **[`tools/generate_flood_tiles.py`](tools/generate_flood_tiles.py)** —
  Terrarium-encoded terrain and RGBA flood-risk XYZ tile pyramids (EPSG:3857)
  for use with web map libraries.
- **[`tools/csv_utils.py`](tools/csv_utils.py)** / **[`tools/tile_utils.py`](tools/tile_utils.py)**
  — shared helpers (CSV/meta loading, tile math).
- **[`tools/mqtt_recorder.py`](tools/mqtt_recorder.py)** /
  **[`tools/mqtt_replayer.py`](tools/mqtt_replayer.py)** — record a live MQTT
  session to JSONL and replay it later with original timing, for demos
  without the real simulator.
- **[`tools/emulator_package/`](tools/emulator_package/)** — packages the
  replayer + a bundled recording into a single standalone executable (no
  Python required) for handing to coworkers. See its
  [README](tools/emulator_package/README.md).

## Testing

```bash
pytest python/tests/visualizer -q
```
