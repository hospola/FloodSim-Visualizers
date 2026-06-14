# DanaSim Viewer (.NET)

ASP.NET Core (.NET 10) web viewer for DanaSim flood simulations. It connects
to the same MQTT protocol as the [Python visualizer](../python/visualizer/),
maintains the simulation grid in memory, and streams live updates to the
browser over SignalR, where the terrain and flood state are rendered in 3D
with X3D/X_ITE.

For the full architecture, design rationale, and MQTT protocol reference, see
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). For deployment-specific
notes (IIS, path resolution, installers), see
[`DEPLOYMENT_FIXES.md`](DEPLOYMENT_FIXES.md).

## Architecture

Hexagonal (ports & adapters), mirroring the Python visualizer's design:

```
src/
├── DanaSim.Viewer.Domain/          # SimulationGrid, Cell, FloodState — no external deps
├── DanaSim.Viewer.Application/     # Handlers, state machine, SimulationAppService
├── DanaSim.Viewer.Infrastructure/  # MQTT adapter, SignalR broadcaster, terrain reader, config
└── DanaSim.Viewer.Web/             # ASP.NET Core host, dashboard, Razor views, wwwroot/js
```

## Running

```bash
dotnet restore DanaSim.Viewer.slnx
dotnet run --project src/DanaSim.Viewer.Web/DanaSim.Viewer.Web.csproj
```

Or via the repo [`Makefile`](../Makefile): `make setup-net` / `make run-net`.

The app serves a configuration dashboard (`/`) for setting the MQTT
broker/scenario, terrain data path and output directory at runtime
(`ApiController`: `GET/POST /api/config`, `POST /api/control/connect|disconnect`,
`GET /api/status`, `GET /api/logs`, `GET /api/runs`), and the 3D viewer at
`/Home/Iframe3D`.

## Configuration

Defaults live in [`src/DanaSim.Viewer.Web/appsettings.json`](src/DanaSim.Viewer.Web/appsettings.json):

| Section | Purpose |
|---|---|
| `Mqtt` | Broker host/port, scenario (`FloodSim/{scenario}/...`), keepalive, `AutoConnect` |
| `Terrain.BasePath` | Parent `data/` directory for IDRISI terrain files (empty = `{app dir}/data`) |
| `FileOutput.OutputDir` | Where rendered output is written |
| `Paths.UserDataDir` | Override for the app's writable data/config/log directory (see `DEPLOYMENT_FIXES.md`) |
| `Simulation.FrameTimeoutMs` | Discard pending frame changes if `FrameEnd` doesn't arrive in time |

Values set via the dashboard are persisted to `user-config.json` under the
app's data directory and override `appsettings.json` on next restart.

## Testing

```bash
dotnet test DanaSim.Viewer.slnx
```

Test projects: `DanaSim.Viewer.Domain.Tests`, `DanaSim.Viewer.Application.Tests`.

## Packaging / Installers

See [`packaging/README.md`](packaging/README.md) for building Linux `.deb`
and Windows installer packages (lite and data-bundled "full" variants).
