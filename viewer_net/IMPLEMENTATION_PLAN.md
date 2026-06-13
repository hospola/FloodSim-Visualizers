# DanaSim Web Viewer — .NET 10 Implementation Plan

## Overview

This document describes the phased implementation plan for the ASP.NET Core 3D visualizer.
The application receives simulation events from a C++ simulator via MQTT, maintains an
in-memory representation of the simulation grid, and streams real-time updates to the browser
using SignalR. The terrain and flood state are rendered in the browser using X3D (via X_ITE).

The Python visualizer already in this repository (`python/visualizer/`) serves as the
authoritative reference for protocol behaviour, grid state logic, and the backpressure
(ChunkAck) mechanism. The .NET implementation mirrors its architecture.

---

## Architecture: Hexagonal (Ports & Adapters)

Hexagonal architecture is chosen because:

- The domain (simulation grid state) must be independent of MQTT, SignalR, and the web
  framework — the same domain logic must be testable without any infrastructure.
- Adapters can be replaced (e.g. swap MQTTnet for another client) without touching
  domain or application code.
- It directly mirrors the Python visualizer's design (`ports.py`, `simulation_app.py`,
  `renderers/base.py`), making the mapping between the two implementations explicit.

```
┌─────────────────────────────────────────────────────────────┐
│                        Web / UI Layer                       │
│           Razor Views  ·  wwwroot/js  ·  x3dom / X_ITE     │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP / WebSocket (SignalR)
┌────────────────────────────▼────────────────────────────────┐
│                    Infrastructure Layer                      │
│  [Input Adapter]  MqttClientAdapter (MQTTnet)               │
│  [Output Adapter] SimulationHub     (SignalR)                │
│  [Output Adapter] MqttControlPublisher (ChunkAck publisher) │
└──────┬─────────────────────────────────────────┬────────────┘
       │ calls                                   │ implements
┌──────▼──────────────────────────────────────────▼──────────┐
│                    Application Layer                        │
│  SimulationAppService  (orchestrates use cases)            │
│  Event Handlers        (one per MQTT event type)           │
│  SimulationStateMachine (protocol lifecycle)               │
│                                                            │
│  [Inbound Port]  ISimulationEventHandler                   │
│  [Outbound Port] ISimulationBroadcaster  → SignalR         │
│  [Outbound Port] IControlPublisher       → MQTT publish    │
└──────────────────────┬─────────────────────────────────────┘
                       │ owns
┌──────────────────────▼─────────────────────────────────────┐
│                      Domain Layer                           │
│  SimulationGrid  ·  Cell  ·  SimulationConfig              │
│  GridMeta        ·  FrameData  ·  FloodState (enum)        │
│  Domain Events:  FrameReady  ·  SimulationEnded            │
└────────────────────────────────────────────────────────────┘
```

### Design patterns used

| Pattern | Where | Purpose |
|---|---|---|
| **Hexagonal / Ports & Adapters** | Whole system | Isolate domain from infrastructure |
| **Strategy** | Event handlers | One class per MQTT event type, selected by `process` field |
| **State Machine** | `SimulationStateMachine` | Enforce protocol phases (Handshake → Init → Running → Ended) |
| **Observer** | Domain → SignalR | Domain raises events; Hub broadcasts to all connected browsers |
| **Factory Method** | `MqttEventFactory` | Deserialise raw MQTT JSON into typed domain commands |
| **Repository** | `SimulationGrid` | Single aggregate root that owns all cell state |
| **DTO** | `*Dto` classes | Separate transport objects (MQTT JSON, SignalR messages) from domain objects |
| **Command** | `PublishChunkAckCommand` | Encapsulate the ChunkAck publish as an explicit value object |

---

## Project Structure

```
viewer_net/
├── DanaSim.Viewer.sln
│
├── src/
│   ├── DanaSim.Viewer.Domain/
│   │   ├── Entities/
│   │   │   ├── SimulationGrid.cs
│   │   │   ├── Cell.cs
│   │   │   └── SimulationConfig.cs
│   │   ├── ValueObjects/
│   │   │   ├── GridMeta.cs
│   │   │   ├── FrameData.cs
│   │   │   └── CellChange.cs
│   │   ├── Enums/
│   │   │   ├── FloodState.cs
│   │   │   └── SimulationPhase.cs
│   │   ├── Events/
│   │   │   ├── FrameReadyEvent.cs
│   │   │   └── SimulationEndedEvent.cs
│   │   └── Ports/
│   │       ├── ISimulationBroadcaster.cs
│   │       └── IControlPublisher.cs
│   │
│   ├── DanaSim.Viewer.Application/
│   │   ├── Services/
│   │   │   └── SimulationAppService.cs
│   │   ├── StateMachine/
│   │   │   └── SimulationStateMachine.cs
│   │   ├── Handlers/
│   │   │   ├── IMqttEventHandler.cs
│   │   │   ├── SystemPingHandler.cs
│   │   │   ├── InitMapConfigHandler.cs
│   │   │   ├── InitAgentLayerHandler.cs
│   │   │   ├── InitAgentEofHandler.cs
│   │   │   ├── FrameStartHandler.cs
│   │   │   ├── EyeSetStateLayerHandler.cs
│   │   │   ├── FrameEndHandler.cs
│   │   │   ├── InitEofHandler.cs
│   │   │   ├── EyeFrameSyncHandler.cs
│   │   │   └── SimEndHandler.cs
│   │   └── Dtos/
│   │       ├── MqttEventDto.cs
│   │       ├── InitMapConfigDto.cs
│   │       ├── InitAgentLayerDto.cs
│   │       ├── FrameStartDto.cs
│   │       ├── EyeSetStateLayerDto.cs
│   │       └── EyeFrameSyncDto.cs
│   │
│   ├── DanaSim.Viewer.Infrastructure/
│   │   ├── Mqtt/
│   │   │   ├── MqttClientAdapter.cs
│   │   │   ├── MqttControlPublisher.cs
│   │   │   └── MqttTopics.cs
│   │   └── SignalR/
│   │       ├── SimulationHub.cs
│   │       └── SignalRBroadcaster.cs
│   │
│   └── DanaSim.Viewer.Web/
│       ├── Controllers/
│       │   └── HomeController.cs
│       ├── Views/Home/
│       │   ├── Index.cshtml
│       │   └── Iframe3D.cshtml
│       ├── wwwroot/js/
│       │   ├── simulation-viewer.js
│       │   └── x3d-scene-manager.js
│       ├── appsettings.json
│       └── Program.cs
│
└── tests/
    ├── DanaSim.Viewer.Domain.Tests/
    ├── DanaSim.Viewer.Application.Tests/
    └── DanaSim.Viewer.Integration.Tests/
```

---

## Technology Stack

| Concern | Library / Version |
|---|---|
| Framework | ASP.NET Core (.NET 10) |
| MQTT client | MQTTnet 4.x |
| Real-time browser comms | ASP.NET Core SignalR (built-in) |
| 3D rendering | X_ITE 11.x (X3D v4, WebGL) |
| JSON deserialisation | System.Text.Json (built-in) |
| Unit testing | xUnit + FluentAssertions |
| Mocking | Moq |
| DI container | Microsoft.Extensions.DependencyInjection (built-in) |

**Why X_ITE over x3dom?** X_ITE actively supports X3D v4, is maintained, and allows
programmatic scene mutation via its JavaScript API — which is required for incremental
frame updates without rebuilding the full scene.

---

## Phases

---

### Phase 1 — Project Setup & Domain Layer

**Goal:** Establish the solution structure and implement the domain with zero external
dependencies. All domain logic must be fully testable in isolation.

#### Tasks

1. Create the solution and four projects with correct project references:
   - `Domain` has no references
   - `Application` references `Domain`
   - `Infrastructure` references `Application` and `Domain`
   - `Web` references `Infrastructure` and `Application`

2. Implement domain entities:
   - `SimulationGrid`: owns cell state array and water depth array; exposes
     `ApplyInitMapConfig`, `ApplyBulkChanges`, `CollectFromLayerEvent`
   - `Cell`: value object with `FloodState` and `WaterDepthM`
   - `SimulationConfig`: grid dimensions, cell resolution, georeference, sim start time

3. Implement value objects:
   - `GridMeta`: rows, cols, cell size, terrain heights
   - `FrameData`: palette grid + water depths snapshot
   - `CellChange`: flat cell index + new state + new height

4. Implement enums:
   - `FloodState`: Dry=0, Risk1..5, Obstacle, ObstacleDestroyed
   - `SimulationPhase`: Disconnected, Handshake, Initialising, Running, Ended

5. Define outbound ports (interfaces only, no implementation):
   - `ISimulationBroadcaster`: `BroadcastFrameAsync(FrameData, GridMeta, string simulationTime)`
   - `IControlPublisher`: `PublishChunkAckAsync()`

6. Define domain events:
   - `FrameReadyEvent`: raised when a render-ready frame is available
   - `SimulationEndedEvent`: raised on Sim_End

#### Tests (Phase 1)
- `SimulationGrid`: apply config, apply bulk changes, boundary cells, empty frame
- `FloodState`: correct int values (protocol uses 0–5)
- `CellChange`: construction and equality

---

### Phase 2 — Application Layer: Protocol Handlers & State Machine

**Goal:** Implement all MQTT event handling logic. This is the core of the application
and the direct equivalent of `simulation_app.py` in the Python visualizer.

#### Tasks

1. Implement `SimulationStateMachine`:
   - Transitions: `Disconnected → Handshake → Initialising → Running → Ended`
   - Throws `InvalidOperationException` if an event arrives in an unexpected phase
     (e.g. `EYE_Frame_Sync` before `Init_EOF`)
   - Exposes `CurrentPhase` property

2. Implement MQTT payload DTOs with `System.Text.Json` attributes (snake_case mapping):
   - One DTO per event type listed in the project structure above

3. Implement `MqttEventFactory`:
   - Reads `process` field from raw JSON
   - Deserialises into the correct DTO and returns a discriminated result
   - Unknown events return a `DiscardedEvent` result (never throw)

4. Implement one `IMqttEventHandler` per event type (Strategy pattern):
   - Each handler receives `SimulationGrid`, `SimulationStateMachine`,
     `IControlPublisher`, and `ISimulationBroadcaster` via constructor injection
   - Key handlers:
     - `FrameStartHandler`: resets pending changes, stores `chunks_per_batch`
     - `EyeSetStateLayerHandler`: accumulates `CellChange` list; calls
       `PublishChunkAckAsync` after every `chunks_per_batch` chunks
     - `FrameEndHandler`: calls `SimulationGrid.ApplyBulkChanges`
     - `InitEofHandler`: triggers first render via `ISimulationBroadcaster`
     - `EyeFrameSyncHandler`: triggers frame render
     - `SimEndHandler`: raises `SimulationEndedEvent`, transitions state machine

5. Implement `SimulationAppService`:
   - Owns `SimulationGrid` and `SimulationStateMachine`
   - Dispatches incoming events to the correct handler via a dictionary
     `Dictionary<string, IMqttEventHandler>`
   - Implements frame timeout: if `FrameEnd` is not received within
     `config.FrameTimeoutSeconds` after `FrameStart`, pending changes are discarded

6. Implement `ISimulationEventHandler` inbound port:
   - `HandleEventAsync(string rawJson)`: entry point called by the MQTT adapter

#### Tests (Phase 2)
- Each handler tested in isolation with mock ports
- State machine: valid transitions, invalid transitions throw
- `MqttEventFactory`: all known event types, unknown events, malformed JSON
- `SimulationAppService`: full init sequence, frame sequence, frame timeout
- Backpressure: ChunkAck published every `chunks_per_batch` chunks, not before

---

### Phase 3 — Infrastructure: MQTT Adapter

**Goal:** Connect the application layer to a real MQTT broker using MQTTnet.

#### Tasks

1. Add MQTTnet 4.x NuGet package to `Infrastructure` project.

2. Implement `MqttTopics` static class:
   ```csharp
   // FloodSim/{scenario}/events
   // FloodSim/{scenario}/system/handshake/ping
   // FloodSim/{scenario}/system/handshake/pong
   // FloodSim/{scenario}/control/events
   ```

3. Implement `MqttClientAdapter`:
   - Connects to broker on startup (host/port from `appsettings.json`)
   - Subscribes to `{base}/events` and `{base}/system/handshake/ping` with QoS 1
   - On message received: calls `ISimulationEventHandler.HandleEventAsync`
   - Reconnects automatically on disconnect (exponential backoff)
   - Registered as `IHostedService` so it starts with the application

4. Implement `MqttControlPublisher` (implements `IControlPublisher`):
   - Publishes `{"process":"ChunkAck"}` to `{base}/control/events` with QoS 1
   - Publishes `{"process":"System_Pong","source":"DanaSim_NetViewer"}` to
     `{base}/system/handshake/pong` in response to `System_Ping`

5. Configuration in `appsettings.json`:
   ```json
   "Mqtt": {
     "Host": "localhost",
     "Port": 1883,
     "Scenario": "scenario_29_10_2024",
     "KeepAliveSeconds": 60,
     "ReconnectDelayMs": 2000
   }
   ```

#### Tests (Phase 3)
- Integration test: start local Mosquitto, publish a sequence of events, verify
  `SimulationAppService` transitions through all phases correctly
- `MqttControlPublisher`: verify ChunkAck payload and topic

---

### Phase 4 — Infrastructure: SignalR Hub & Web Layer

**Goal:** Implement the output adapter (SignalR) and wire up the ASP.NET Core web
application with DI, routing, and the Razor views.

#### Tasks

1. Implement `SimulationHub` (extends `Hub`):
   - Client-callable method: `JoinSimulation(string scenario)`
   - Server-to-client messages:
     - `"InitialState"`: sent on `Init_EOF` — full grid state, terrain heights,
       grid dimensions
     - `"FrameUpdate"`: sent on `EYE_Frame_Sync` — list of changed cells + sim time
     - `"SimulationEnded"`: sent on `Sim_End`

2. Implement `SignalRBroadcaster` (implements `ISimulationBroadcaster`):
   - Injected with `IHubContext<SimulationHub>`
   - `BroadcastFrameAsync`: sends to all clients in the scenario group

3. Define SignalR message DTOs (separate from MQTT DTOs):
   - `InitialStateMessage`: `{ gridMeta, cells[], terrain[] }`
   - `FrameUpdateMessage`: `{ simulationTime, changes[{ index, state, height }] }`

4. `Program.cs` DI registration:
   - `AddSignalR()`
   - `AddSingleton<SimulationGrid>()`
   - `AddSingleton<SimulationStateMachine>()`
   - `AddSingleton<SimulationAppService>()`
   - `AddScoped` all handlers
   - `AddSingleton<ISimulationBroadcaster, SignalRBroadcaster>()`
   - `AddSingleton<IControlPublisher, MqttControlPublisher>()`
   - `AddHostedService<MqttClientAdapter>()`

5. `HomeController`:
   - `GET /` → `Index.cshtml`
   - `GET /Home/Iframe3D` → `Iframe3D.cshtml`

6. Basic Razor views (layout only, no JS yet):
   - `Iframe3D.cshtml`: contains the `<x3d>` root element and SignalR script imports

#### Tests (Phase 4)
- `SignalRBroadcaster`: verify correct hub method name and payload shape
- DI smoke test: resolve `SimulationAppService` from service provider

---

### Phase 5 — Frontend: Real-Time 3D Visualisation

**Goal:** Implement the browser-side JavaScript that connects to SignalR and updates
the X3D scene incrementally.

#### Tasks

1. Include X_ITE via CDN in `Iframe3D.cshtml`:
   ```html
   <script src="https://cdn.jsdelivr.net/npm/x_ite@latest/dist/x_ite.min.js"></script>
   ```

2. Implement `x3d-scene-manager.js`:
   - `buildInitialScene(initialStateMessage)`:
     - Creates an X3D `IndexedFaceSet` (or `ElevationGrid`) for terrain using
       `terrain[]` heights and `gridMeta`
     - Creates a per-cell colour array from initial flood states
     - Inserts into the `<X3D>` element
   - `applyFrameUpdate(frameUpdateMessage)`:
     - Iterates `changes[]` and updates colour/height of affected cells in-place
     - Does NOT rebuild the scene — only mutates existing X3D node attributes
   - `showSimulationEnded()`: displays an overlay

3. Implement `simulation-viewer.js`:
   - Connects to SignalR hub: `new signalR.HubConnectionBuilder().withUrl("/simulationHub")`
   - On `"InitialState"`: calls `buildInitialScene`
   - On `"FrameUpdate"`: calls `applyFrameUpdate`
   - On `"SimulationEnded"`: calls `showSimulationEnded`
   - Handles connection drops with automatic reconnect

4. Flood state colour palette (matches Python visualizer `colors.py`):
   - State 0 (Dry): transparent / terrain colour
   - States 1–5: blue gradient from light to deep (risk levels)
   - Obstacle: grey
   - ObstacleDestroyed: dark red

#### Tests (Phase 5)
- Manual browser test against local Mosquitto + C++ simulator
- Verify: correct initial render on `Init_EOF`, incremental updates on each frame,
  no full scene rebuild between frames

---

### Phase 6 — Integration, Hardening & Handover

**Goal:** End-to-end validation with the real simulator, error handling, and preparation
for handover to the team repository.

#### Tasks

1. End-to-end test with C++ simulator:
   - Full `scenario_29_10_2024` run
   - Verify all protocol phases complete without errors
   - Verify browser renders ~400k-cell initial state without timeout

2. Error handling:
   - Broker unavailable on startup: retry with backoff, log warning, do not crash
   - Malformed MQTT payload: log and discard, do not crash application
   - Browser disconnects mid-simulation: reconnect and receive next `FrameUpdate`
   - `FrameStart` without subsequent `FrameEnd` (frame timeout): discard pending
     changes and log warning (mirrors Python `on_idle` logic)

3. Configuration validation on startup:
   - Fail fast if `Mqtt:Host` is missing or `Mqtt:Scenario` is empty

4. Logging:
   - Structured logging via `Microsoft.Extensions.Logging`
   - Log level `Information` for phase transitions
   - Log level `Warning` for frame timeouts and reconnects
   - Log level `Debug` for individual ChunkAck events

5. Prepare for repository merge:
   - Confirm project builds and tests pass: `dotnet build` + `dotnet test`
   - Review with team: DI wiring, appsettings, SignalR hub route (`/simulationHub`)

#### Tests (Phase 6)
- Integration: broker reconnect
- Integration: frame timeout recovery
- Load: 10 consecutive frames with max-size batches (400k cells each)

---

## MQTT Protocol Reference (summary)

All topics follow `FloodSim/{scenario}/...`

| Topic | Direction | Purpose |
|---|---|---|
| `.../system/handshake/ping` | Simulator → Viewer | Ping |
| `.../system/handshake/pong` | Viewer → Simulator | Pong response |
| `.../events` | Simulator → Viewer | All init and simulation events |
| `.../control/events` | Viewer → Simulator | ChunkAck backpressure |

Event order: `System_Ping` → `System_Pong` → `InitMap_Config` → `InitAgent_Layer` ×N
→ `InitAgent_EOF` → `FrameStart` → `EYE_SetState_Layer` ×N (+ `ChunkAck` every batch)
→ `Init_EOF` → [`FrameStart` → `EYE_SetState_Layer` ×N → `FrameEnd` → `EYE_Frame_Sync`] ×frames
→ `Sim_End`

QoS 1 for all events. Chunk size: up to 40,000 cells per `EYE_SetState_Layer`.
Batch size: 10 chunks → up to 400,000 cells per `ChunkAck` cycle (~16 MB JSON).

---

## Open Questions (to resolve with team)

| # | Question | Impact |
|---|---|---|
| 1 | MQTT broker host/IP in production (`sdlpspand.sdlps.com`) | Phase 3 config |
| 2 | Where are terrain data files (`topo_bathy`, `water_depth`) on the server? | Phase 2 `InitAgentLayerHandler` |
| 3 | Access to Pau's repository | Phase 6 merge |

---

## Reference: Python Visualizer Mapping

| Python (`python/visualizer/`) | .NET equivalent |
|---|---|
| `ports.py` → `SimulationEventHandler` | `ISimulationEventHandler` (inbound port) |
| `ports.py` → `ControlPublisher` | `IControlPublisher` (outbound port) |
| `renderers/base.py` → `BaseRenderer` | `ISimulationBroadcaster` (outbound port) |
| `simulation_app.py` → `SimulationApp` | `SimulationAppService` + all handlers |
| `data_model.py` → `SimulationGrid` | `Domain/Entities/SimulationGrid.cs` |
| `network.py` | `MqttClientAdapter.cs` |
| `renderers/x3d/` | `wwwroot/js/x3d-scene-manager.js` |
