"""MQTT traffic replayer ("emulator") for DanaSim.

Replays a recording captured with ``mqtt_recorder.py`` back onto the broker,
preserving (or scaling) the original inter-message timing. This lets the
visualizer be demoed without running the real (slow) simulator core.

Usage:
    python mqtt_replayer.py recording.jsonl
    python mqtt_replayer.py recording.jsonl --speed 4 --loop
    python mqtt_replayer.py recording.jsonl --scenario demo_run
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt


def load_records(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def replay(records: list[dict], host: str = "localhost", port: int = 1883,
           speed: float = 1.0, max_gap: float | None = None,
           loop: bool = False, scenario: str | None = None) -> None:
    """Publish a recorded sequence of MQTT messages back onto a broker."""

    def rewrite_topic(topic: str) -> str:
        if scenario is None:
            return topic
        parts = topic.split("/")
        if len(parts) >= 2 and parts[0] == "FloodSim":
            parts[1] = scenario
        return "/".join(parts)

    def rewrite_payload(raw: str) -> str:
        if scenario is None:
            return raw
        try:
            payload = json.loads(raw)
        except Exception:
            return raw
        if isinstance(payload, dict) and "scenario" in payload:
            payload["scenario"] = scenario
            return json.dumps(payload)
        return raw

    # paho-mqtt 2.x requires callback_api_version; 1.x doesn't have the enum.
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,
                              client_id="DanaSim_Emulator", clean_session=True)
    else:
        client = mqtt.Client(client_id="DanaSim_Emulator", clean_session=True)
    client.connect(host, port, 60)
    client.loop_start()

    try:
        run = 0
        while True:
            run += 1
            if run > 1:
                print("Looping recording...")
            for i, rec in enumerate(records, start=1):
                dt = rec["dt"]
                if max_gap is not None:
                    dt = min(dt, max_gap)
                if dt > 0:
                    time.sleep(dt / speed)

                topic = rewrite_topic(rec["topic"])
                payload = rewrite_payload(rec["payload_raw"])
                client.publish(topic, payload=payload, qos=rec.get("qos", 1),
                                retain=rec.get("retain", False))
                print(f"[{i:04d}/{len(records)}] -> {topic}")

            if not loop:
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a recorded DanaSim MQTT session")
    parser.add_argument("recording", help="JSONL file produced by mqtt_recorder.py")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--speed", type=float, default=1.0,
                         help="playback speed multiplier (2.0 = twice as fast, default 1.0)")
    parser.add_argument("--max-gap", type=float, default=None,
                         help="cap any single inter-message delay to this many seconds")
    parser.add_argument("--loop", action="store_true", help="replay the recording repeatedly")
    parser.add_argument("--scenario", default=None,
                         help="rewrite the scenario name in topics and JSON payloads")
    args = parser.parse_args()

    records = load_records(args.recording)
    print(f"Loaded {len(records)} messages from {args.recording}")

    replay(records, host=args.host, port=args.port, speed=args.speed,
           max_gap=args.max_gap, loop=args.loop, scenario=args.scenario)


if __name__ == "__main__":
    main()
