# DanaSim MQTT Demo Emulator

A standalone tool that replays a **recorded real simulation session** back
onto an MQTT broker, with the original timing. It lets you demo the
visualizer without running the (slow) simulator core.

It bundles:
- `emulator_app.py` / `mqtt_replayer.py` — the replay logic
- `recording.jsonl` — a captured session (62 messages: handshake → init →
  frames → `Sim_End`, scenario `demo`)

Everything (Python runtime + `paho-mqtt` + the recording) is packed into a
single file per OS that coworkers can run with **no Python installation**.

---

## Running it

```bash
# Linux
./floodsim-emulator

# Windows
floodsim-emulator.exe
```

By default it connects to `localhost:1883` and replays the bundled
recording in real time under the topics it was recorded with
(`FloodSim/demo/...`). On startup it prints the broker target and topic
it's about to use.

> On Windows, `floodsim-emulator.exe` is a self-extracting launcher: it
> silently unpacks to `%TEMP%\floodsim-emulator` and opens a console
> window running the emulator. Closing that console stops it.

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `--host HOST` | `localhost` | MQTT broker address |
| `--port PORT` | `1883` | MQTT broker port |
| `--speed N` | `1.0` | Playback speed multiplier (e.g. `4` = 4x faster) |
| `--max-gap SECONDS` | none | Cap any single inter-message delay (useful to skip long idle waits) |
| `--loop` | off | Replay the recording repeatedly, forever |
| `--scenario NAME` | none | Rewrite `FloodSim/demo/...` topics and JSON `scenario` fields to `FloodSim/NAME/...` |
| `--recording PATH` | bundled `recording.jsonl` | Use a different recording instead of the bundled one |

### Examples

```bash
# Demo booth: loop forever at 5x speed
./floodsim-emulator --loop --speed 5

# Broker on another machine
./floodsim-emulator --host 192.168.1.50

# Visualizer is configured with a different scenario name
./floodsim-emulator --scenario scenario_29_10_2024
```

On Windows, pass arguments the same way:
```cmd
floodsim-emulator.exe --loop --speed 5
```

### Matching the visualizer's scenario

The recording was captured under scenario `demo`. For the visualizer to
react to it, its `mqtt.yml` must have:

```yaml
mqtt:
  scenario: demo
```

...or run the emulator with `--scenario <name>` matching whatever
`mqtt.scenario` is set to in the visualizer's config. The emulator prints
the topic it's about to use on startup, e.g.:

```
Scenario topic: FloodSim/demo/...
```

---

## Building

Each platform's artifact must be built on/for that platform.

### Linux → `dist/floodsim-emulator`

Uses PyInstaller (requires Python 3 + pip).

```bash
./build_linux.sh
```

The script handles a known issue on some hardened kernels (e.g. Debian 13)
where the bundled `libpython` has an executable-stack ELF flag the kernel
rejects — it detects the failure, patches the flag, and rebuilds
automatically.

### Windows → `dist/floodsim-emulator.exe`

Can be built **from Linux** (no Wine needed). PyInstaller can't
cross-compile, so instead this downloads the official Windows-embeddable
Python runtime + the `paho-mqtt` wheel, bundles them with the emulator
scripts and recording, and wraps everything into a single self-extracting
executable using NSIS (`makensis`).

Requires: `makensis` (`apt install nsis`), `pip`, internet access.

```bash
./build_windows.sh
```

Internals:
- `windows_build/` — scratch directory (downloaded Python runtime, wheels,
  assembled payload). Safe to delete; regenerated each run.
- `floodsim-emulator.nsi` — the NSIS script that packages
  `windows_build/payload/` into `dist/floodsim-emulator.exe`. On launch it
  silently extracts to `%TEMP%\floodsim-emulator` and runs
  `python\python.exe emulator_app.py <args>`.

---

## Updating the bundled recording

1. Capture a new session with `mqtt_recorder.py`:
   ```bash
   python ../mqtt_recorder.py --scenario <scenario> --output recording.jsonl
   ```
   Run this while the visualizer and simulator are both running, *before*
   the simulator starts its handshake, so the full sequence is captured.
   It auto-stops on `Sim_End`.

2. Copy the resulting `recording.jsonl` into this folder, replacing the
   existing one.

3. Rebuild (`./build_linux.sh` and/or `./build_windows.sh`). The new
   recording gets bundled automatically.

---

## Distributing

Send the single built file (`floodsim-emulator` or `floodsim-emulator.exe`)
to coworkers — that's the entire deliverable. No Python, no MQTT library,
no extra files needed on their end.
