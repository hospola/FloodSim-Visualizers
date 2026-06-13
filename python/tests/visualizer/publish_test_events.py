"""Test MQTT publisher for DanaSim visualizer integration/e2e tests.

Publishes a complete, protocol-correct simulation sequence:
  handshake → init → N simulation frames → Sim_End

Cell format uses the current protocol: flat-index string keys in a dict.
  {"flat_index": {"state": "FLOODED", "height": 0.3}}

Usage:
    python publish_test_events.py --scenario test --frames 3 --cols 10 --rows 8
"""
import argparse
import json
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_topics(scenario: str) -> dict:
    base = f"FloodSim/{scenario}"
    return {
        "events":  f"{base}/events",
        "ping":    f"{base}/system/handshake/ping",
        "pong":    f"{base}/system/handshake/pong",
        "control": f"{base}/control/events",
    }


def _pub(client, topic: str, payload: dict, qos: int) -> None:
    client.publish(topic, payload=json.dumps(payload), qos=qos)
    time.sleep(0.02)  # small delay to avoid broker overload in tests


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish test MQTT events for DanaSim")
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=1883)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--qos",      type=int, default=1)
    parser.add_argument("--wait-pong", type=float, default=5.0,
                        help="Seconds to wait for System_Pong before continuing")
    parser.add_argument("--rows",     type=int, default=8)
    parser.add_argument("--cols",     type=int, default=10)
    parser.add_argument("--frames",   type=int, default=2,
                        help="Number of simulation frames to publish")
    parser.add_argument("--wet-cells", type=int, default=5,
                        help="Number of wet cells per frame")
    args = parser.parse_args()

    topics = build_topics(args.scenario)
    got_pong = {"value": False}

    client = mqtt.Client(
        client_id=f"DanaSim_TestPublisher_{args.scenario}", clean_session=True
    )

    def on_connect(cli, userdata, flags, rc):
        if rc == 0:
            cli.subscribe(topics["pong"], qos=args.qos)

    def on_message(cli, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if payload.get("process") == "System_Pong":
                got_pong["value"] = True
                print("Received System_Pong")
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, 60)
    client.loop_start()

    try:
        # --- Handshake ---
        _pub(client, topics["ping"], {
            "process": "System_Ping",
            "source":  "Test_Publisher",
            "scenario": args.scenario,
            "timestamp_utc": utc_now_iso(),
        }, args.qos)
        print(f"Published System_Ping to {topics['ping']}")

        deadline = time.time() + args.wait_pong
        while time.time() < deadline and not got_pong["value"]:
            time.sleep(0.05)
        if not got_pong["value"]:
            print("Warning: no System_Pong received — continuing anyway")

        # --- Initialization ---
        _pub(client, topics["events"], {
            "process": "InitMap_Config",
            "source":  "Test_Publisher",
            "scenario": args.scenario,
            "timestamp_utc": utc_now_iso(),
            "map": {
                "size_x": args.cols,
                "size_y": args.rows,
                "chunk_size": 10,
                "cell_resolution_m": 5.0,
            },
            "metadata": {"sim_start_time": utc_now_iso(), "time_step_s": 1.0},
        }, args.qos)
        print("Published InitMap_Config")

        _pub(client, topics["events"], {
            "process": "InitAgent_EOF",
            "source":  "Test_Publisher",
            "scenario": args.scenario,
            "timestamp_utc": utc_now_iso(),
        }, args.qos)
        print("Published InitAgent_EOF")

        # Initial state (empty grid) — FrameStart + FrameEnd + Init_EOF
        _pub(client, topics["events"], {
            "process": "FrameStart",
            "total_chunks": 0,
            "chunks_per_batch": 0,
        }, args.qos)

        _pub(client, topics["events"], {
            "process": "FrameEnd",
        }, args.qos)

        _pub(client, topics["events"], {
            "process": "Init_EOF",
            "source":  "Test_Publisher",
            "scenario": args.scenario,
            "timestamp_utc": utc_now_iso(),
            "total_chunks_sent": 0,
        }, args.qos)
        print("Published Init_EOF")

        # --- Simulation frames ---
        states = ["FLOODED", "HIGH_DEPTH", "MEDIUM_DEPTH", "LOW_DEPTH", "VERY_SHALLOW"]
        for frame_idx in range(args.frames):
            n_wet = min(args.wet_cells, args.rows * args.cols)

            _pub(client, topics["events"], {
                "process": "FrameStart",
                "total_chunks": 1,
                "chunks_per_batch": 0,
            }, args.qos)

            # Build wet cells using flat indices (current protocol)
            cells = {}
            for i in range(n_wet):
                flat_idx = (frame_idx * n_wet + i) % (args.rows * args.cols)
                state = states[i % len(states)]
                cells[str(flat_idx)] = {"state": state, "height": 0.1 * (i + 1)}

            _pub(client, topics["events"], {
                "process": "EYE_SetState_Layer",
                "source":  "Test_Publisher",
                "scenario": args.scenario,
                "timestamp_utc": utc_now_iso(),
                "id": "CellState",
                "changes": {"cells": cells},
            }, args.qos)

            _pub(client, topics["events"], {
                "process": "FrameEnd",
            }, args.qos)

            _pub(client, topics["events"], {
                "process": "EYE_Frame_Sync",
                "source":  "Test_Publisher",
                "scenario": args.scenario,
                "timestamp_utc": utc_now_iso(),
                "simulation_time": utc_now_iso(),
            }, args.qos)
            print(f"Published frame {frame_idx + 1}/{args.frames} ({n_wet} wet cells)")

        # --- End ---
        _pub(client, topics["events"], {
            "process": "Sim_End",
            "source":  "Test_Publisher",
            "scenario": args.scenario,
            "timestamp_utc": utc_now_iso(),
            "sim_time_total": float(args.frames),
        }, args.qos)
        print("Published Sim_End")

    finally:
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
