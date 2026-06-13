"""MQTT traffic recorder for DanaSim.

Subscribes to every topic under ``FloodSim/<scenario>/#`` (events, system
handshake, control) and writes each message to a JSONL file together with
the time elapsed since the previous message. The recording can later be
replayed with ``mqtt_replayer.py`` to demo the visualizer without running
the (slow) simulator core.

Usage:
    python mqtt_recorder.py --scenario scenario_29_10_2024 --output recording.jsonl
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt


def main() -> None:
    parser = argparse.ArgumentParser(description="Record DanaSim MQTT traffic for later replay")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--topic", default=None,
                         help="topic filter to subscribe to (default: FloodSim/<scenario>/#)")
    parser.add_argument("--stop-on", default="Sim_End",
                         help="stop recording once a message with this 'process' value arrives")
    args = parser.parse_args()

    topic_filter = args.topic or f"FloodSim/{args.scenario}/#"

    state = {"last_time": None, "count": 0, "done": False}

    def on_connect(client, userdata, flags, rc):
        client.subscribe(topic_filter, qos=1)
        print(f"Subscribed to {topic_filter}")

    def on_message(client, userdata, msg):
        now = time.monotonic()
        dt = 0.0 if state["last_time"] is None else now - state["last_time"]
        state["last_time"] = now

        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = None

        record = {
            "dt": dt,
            "topic": msg.topic,
            "qos": msg.qos,
            "retain": msg.retain,
            "payload_raw": raw,
        }
        out_file.write(json.dumps(record) + "\n")
        out_file.flush()

        state["count"] += 1
        process = payload.get("process") if isinstance(payload, dict) else None
        print(f"[{state['count']:04d}] dt={dt:7.3f}s topic={msg.topic} process={process}")

        if process == args.stop_on:
            state["done"] = True

    client = mqtt.Client(client_id=f"DanaSim_Recorder_{args.scenario}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, 60)
    client.loop_start()

    print(f"Recording to {args.output}. Press Ctrl+C to stop early "
          f"(auto-stops on '{args.stop_on}').")

    with open(args.output, "w", encoding="utf-8") as out_file:
        try:
            while not state["done"]:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            client.loop_stop()
            client.disconnect()

    print(f"Saved {state['count']} messages to {args.output}")


if __name__ == "__main__":
    main()
