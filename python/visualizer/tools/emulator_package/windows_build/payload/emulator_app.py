"""DanaSim MQTT demo emulator.

Standalone entry point (built with PyInstaller) that replays a bundled
recording of a real simulation session onto an MQTT broker, so the
visualizer can be demoed without running the (slow) simulator core.

Usage (once built as floodsim-emulator / floodsim-emulator.exe):
    floodsim-emulator --host 192.168.1.10
    floodsim-emulator --speed 4 --loop
    floodsim-emulator --scenario demo_run
"""
import argparse
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _BUNDLE_DIR = Path(sys._MEIPASS)
else:
    _BUNDLE_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(_BUNDLE_DIR.parent))

from mqtt_replayer import load_records, replay

_BUNDLED_RECORDING = _BUNDLE_DIR / "recording.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="DanaSim MQTT demo emulator")
    parser.add_argument("--host", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--speed", type=float, default=1.0,
                         help="playback speed multiplier (2.0 = twice as fast, default 1.0)")
    parser.add_argument("--max-gap", type=float, default=None,
                         help="cap any single inter-message delay to this many seconds")
    parser.add_argument("--loop", action="store_true", help="replay the recording repeatedly")
    parser.add_argument("--scenario", default=None,
                         help="rewrite the scenario name in topics and JSON payloads")
    parser.add_argument("--recording", default=None,
                         help="use a custom recording instead of the bundled one")
    args = parser.parse_args()

    recording_path = args.recording or str(_BUNDLED_RECORDING)
    records = load_records(recording_path)

    base_topics = sorted({rec["topic"].split("/", 2)[1] for rec in records
                           if rec["topic"].startswith("FloodSim/")})
    scenario_label = args.scenario or "/".join(base_topics) or "?"

    print(f"Loaded {len(records)} messages from {recording_path}")
    print(f"Target broker:  {args.host}:{args.port}")
    print(f"Scenario topic: FloodSim/{scenario_label}/...")
    print("(make sure the visualizer's mqtt.yml 'scenario' matches this name, "
          "or pass --scenario to override)")

    replay(records, host=args.host, port=args.port, speed=args.speed,
           max_gap=args.max_gap, loop=args.loop, scenario=args.scenario)


if __name__ == "__main__":
    main()
