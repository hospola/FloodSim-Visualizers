# FloodSim Visualizers

Real-time and offline visualization tooling for **DanaSim**, a flood
simulation system. This repository contains two independent visualizer
implementations that consume the same MQTT protocol emitted by the DanaSim
C++ simulator core and render the evolving flood state:

- **[`python/visualizer/`](python/visualizer/)** — a Python MQTT monitor with
  pluggable renderers (CSV, 2D/Matplotlib, 3D/X3D), plus offline tooling for
  generating map tiles, X3D heightmaps, and a CesiumJS-based viewer.
- **[`viewer_net/`](viewer_net/)** — an ASP.NET Core (.NET 10) web viewer that
  streams live updates to the browser over SignalR and renders the terrain
  and flood state in 3D with X3D/X_ITE.

> Developed as part of a Bachelor's thesis (TFG) project.

---

## How it fits together

```
┌──────────────────┐        MQTT (FloodSim/{scenario}/...)        ┌──────────────────────┐
│  DanaSim          │ ───────────────────────────────────────────▶│  Visualizer           │
│  simulator core   │◀─────────────────────────────────────────── │  (Python or .NET)     │
│  (C++, external)  │     handshake / ChunkAck backpressure        │                       │
└──────────────────┘                                               └──────────┬────────────┘
                                                                                │
                                                       renders to: CSV / PNG / X3D / browser (SignalR + X_ITE)
```

Both visualizers implement the **same protocol** (handshake → map/terrain
init → per-frame flood-state updates → simulation end) over MQTT topics under
`FloodSim/{scenario}/...`. The Python implementation is the original/reference
implementation; the .NET implementation mirrors its architecture using a
hexagonal (ports & adapters) design — see
[`viewer_net/IMPLEMENTATION_PLAN.md`](viewer_net/IMPLEMENTATION_PLAN.md) for
the full protocol reference and design rationale.

Neither visualizer requires the actual simulator to run: a recorded session
can be replayed onto a local MQTT broker using the bundled emulator (see
[`python/visualizer/tools/emulator_package/`](python/visualizer/tools/emulator_package/)).

---

## Repository layout

```
.
├── python/
│   ├── visualizer/        # Python MQTT monitor + renderers + offline tools
│   └── tests/visualizer/  # pytest suite
├── viewer_net/
│   ├── src/                # ASP.NET Core app (Domain / Application / Infrastructure / Web)
│   ├── tests/               # xUnit test projects
│   └── packaging/          # Linux .deb / Windows installer build scripts
├── config/                 # Sample DanaSim simulator configs (referenced by mqtt.yml)
└── Makefile                # Convenience targets for both stacks
```

---

## Quickstart

### Prerequisites

- Python 3.12+
- .NET 10 SDK (only needed for the `viewer_net` viewer)
- An MQTT broker (e.g. [Mosquitto](https://mosquitto.org/)) running on
  `localhost:1883` for live use — not required for the offline demo/tools

### Using the Makefile

```bash
make setup          # creates .venv, installs Python deps, dotnet restore
make run-python      # runs the Python MQTT monitor (python/visualizer)
make run-net          # runs the ASP.NET Core web viewer
make test             # runs both test suites
```

### Try it without a simulator

The Python visualizer ships a synthetic demo that needs no MQTT broker:

```bash
.venv/bin/python -m python.visualizer.demo --renderer x3d --output ./demo_output
```

To exercise the full MQTT pipeline (both visualizers) without the real
simulator, replay a recorded session with the bundled emulator — see
[`python/visualizer/tools/emulator_package/README.md`](python/visualizer/tools/emulator_package/README.md).

---

## Documentation

| Doc | Covers |
|---|---|
| [`python/visualizer/README.md`](python/visualizer/README.md) | Python monitor: renderers, depth providers, config, offline tile/X3D tools |
| [`viewer_net/IMPLEMENTATION_PLAN.md`](viewer_net/IMPLEMENTATION_PLAN.md) | .NET viewer architecture, MQTT protocol reference, phased implementation plan |
| [`viewer_net/DEPLOYMENT_FIXES.md`](viewer_net/DEPLOYMENT_FIXES.md) | Deployment notes (IIS, path resolution, installers) |
| [`viewer_net/packaging/README.md`](viewer_net/packaging/README.md) | Building Linux/Windows installers |
| [`python/visualizer/tools/emulator_package/README.md`](python/visualizer/tools/emulator_package/README.md) | Standalone MQTT session replay tool for demos |

---

## Testing

```bash
make test-python   # pytest, python/tests/visualizer
make test-net      # dotnet test, viewer_net/DanaSim.Viewer.slnx
```

CI runs both suites plus a SonarCloud scan on `main` (see
[`.github/workflows/tests.yml`](.github/workflows/tests.yml)).

## License

MIT — see [LICENSE](LICENSE).
