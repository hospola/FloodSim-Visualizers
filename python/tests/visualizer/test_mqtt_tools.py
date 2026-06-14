"""Tests for tools/mqtt_recorder.py and tools/mqtt_replayer.py (mocked paho)."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from python.visualizer.tools import mqtt_replayer
from python.visualizer.tools.mqtt_replayer import load_records, replay


# ===========================================================================
# mqtt_replayer.load_records
# ===========================================================================

class TestLoadRecords:
    def test_loads_jsonl_skipping_blank_lines(self, tmp_path) -> None:
        f = tmp_path / "recording.jsonl"
        f.write_text('{"a": 1}\n\n{"a": 2}\n')

        records = load_records(str(f))

        assert records == [{"a": 1}, {"a": 2}]

    def test_empty_file_returns_empty_list(self, tmp_path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("")

        assert load_records(str(f)) == []


# ===========================================================================
# mqtt_replayer.replay
# ===========================================================================

def _record(topic="FloodSim/demo/events", payload=None, dt=0.0, qos=1, retain=False) -> dict:
    return {
        "dt": dt,
        "topic": topic,
        "qos": qos,
        "retain": retain,
        "payload_raw": json.dumps(payload if payload is not None else {"process": "Frame"}),
    }


class TestReplay:
    def test_publishes_each_record_and_disconnects(self) -> None:
        mock_client = MagicMock()
        records = [_record()]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep"):
            replay(records, loop=False)

        mock_client.connect.assert_called_once_with("localhost", 1883, 60)
        mock_client.loop_start.assert_called_once()
        mock_client.publish.assert_called_once_with(
            "FloodSim/demo/events", payload=records[0]["payload_raw"], qos=1, retain=False)
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_sleeps_for_dt_scaled_by_speed(self) -> None:
        mock_client = MagicMock()
        records = [_record(dt=2.0)]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep") as mock_sleep:
            replay(records, speed=4.0, loop=False)

        mock_sleep.assert_any_call(pytest.approx(0.5))

    def test_max_gap_caps_sleep_duration(self) -> None:
        mock_client = MagicMock()
        records = [_record(dt=100.0)]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep") as mock_sleep:
            replay(records, max_gap=5.0, loop=False)

        mock_sleep.assert_any_call(pytest.approx(5.0))

    def test_zero_dt_does_not_sleep(self) -> None:
        mock_client = MagicMock()
        records = [_record(dt=0.0)]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep") as mock_sleep:
            replay(records, loop=False)

        # The only sleep call should be the trailing shutdown delay (0.3s),
        # not one for the zero-length inter-message gap.
        mock_sleep.assert_called_once_with(0.3)

    def test_scenario_rewrites_topic_and_payload(self) -> None:
        mock_client = MagicMock()
        records = [_record(
            topic="FloodSim/demo/events",
            payload={"process": "Frame", "scenario": "demo"},
        )]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep"):
            replay(records, scenario="custom", loop=False)

        args, kwargs = mock_client.publish.call_args
        assert args[0] == "FloodSim/custom/events"
        assert json.loads(kwargs["payload"])["scenario"] == "custom"

    def test_scenario_rewrite_leaves_unrelated_topics_untouched(self) -> None:
        mock_client = MagicMock()
        records = [_record(topic="Other/topic", payload={"process": "Frame"})]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep"):
            replay(records, scenario="custom", loop=False)

        args, _ = mock_client.publish.call_args
        assert args[0] == "Other/topic"

    def test_payload_rewrite_skips_non_json_payloads(self) -> None:
        mock_client = MagicMock()
        records = [{
            "dt": 0.0, "topic": "FloodSim/demo/events",
            "qos": 1, "retain": False, "payload_raw": "not json",
        }]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep"):
            replay(records, scenario="custom", loop=False)

        _, kwargs = mock_client.publish.call_args
        assert kwargs["payload"] == "not json"

    def test_loop_stops_on_keyboard_interrupt(self) -> None:
        mock_client = MagicMock()
        mock_client.publish.side_effect = [None, KeyboardInterrupt]
        records = [_record()]

        with patch.object(mqtt_replayer.mqtt, "Client", return_value=mock_client), \
             patch.object(mqtt_replayer.time, "sleep"):
            replay(records, loop=True)

        assert mock_client.publish.call_count == 2
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()


# ===========================================================================
# mqtt_replayer.main
# ===========================================================================

class TestReplayerMain:
    def test_main_loads_and_replays(self, tmp_path, monkeypatch) -> None:
        from python.visualizer.tools import mqtt_replayer as mod

        f = tmp_path / "recording.jsonl"
        f.write_text(json.dumps(_record()) + "\n")

        monkeypatch.setattr(sys, "argv", ["mqtt_replayer", str(f)])

        with patch.object(mod, "replay") as mock_replay:
            mod.main()

        mock_replay.assert_called_once()
        records_arg = mock_replay.call_args.args[0]
        assert len(records_arg) == 1


# ===========================================================================
# mqtt_recorder.main
# ===========================================================================

class TestRecorderMain:
    def test_records_message_and_stops_on_sim_end(self, tmp_path, monkeypatch) -> None:
        from python.visualizer.tools import mqtt_recorder as mod

        out_file = tmp_path / "recording.jsonl"
        mock_paho = MagicMock()

        monkeypatch.setattr(sys, "argv", [
            "mqtt_recorder", "--scenario", "demo", "--output", str(out_file),
        ])

        def fake_sleep(_secs):
            msg = MagicMock()
            msg.topic = "FloodSim/demo/events"
            msg.qos = 1
            msg.retain = False
            msg.payload = json.dumps({"process": "Sim_End"}).encode("utf-8")
            mock_paho.on_message(mock_paho, None, msg)

        with patch("paho.mqtt.client.Client", return_value=mock_paho) as mock_cls, \
             patch.object(mod.time, "sleep", side_effect=fake_sleep), \
             patch.object(mod.time, "monotonic", return_value=1.0):
            mod.main()

        mock_cls.assert_called_once_with(client_id="DanaSim_Recorder_demo", clean_session=True)
        mock_paho.connect.assert_called_once_with("localhost", 1883, 60)
        mock_paho.loop_start.assert_called_once()
        mock_paho.loop_stop.assert_called_once()
        mock_paho.disconnect.assert_called_once()

        lines = out_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["topic"] == "FloodSim/demo/events"
        assert record["dt"] == 0.0

    def test_on_connect_subscribes_to_scenario_topic(self, tmp_path, monkeypatch) -> None:
        from python.visualizer.tools import mqtt_recorder as mod

        out_file = tmp_path / "recording.jsonl"
        mock_paho = MagicMock()

        monkeypatch.setattr(sys, "argv", [
            "mqtt_recorder", "--scenario", "demo", "--output", str(out_file),
        ])

        def fake_sleep(_secs):
            mock_paho.on_connect(mock_paho, None, None, 0)
            msg = MagicMock()
            msg.topic = "FloodSim/demo/events"
            msg.qos = 1
            msg.retain = False
            msg.payload = json.dumps({"process": "Sim_End"}).encode("utf-8")
            mock_paho.on_message(mock_paho, None, msg)

        with patch("paho.mqtt.client.Client", return_value=mock_paho), \
             patch.object(mod.time, "sleep", side_effect=fake_sleep), \
             patch.object(mod.time, "monotonic", return_value=1.0):
            mod.main()

        mock_paho.subscribe.assert_called_once_with("FloodSim/demo/#", qos=1)

    def test_on_message_handles_non_json_payload(self, tmp_path, monkeypatch) -> None:
        from python.visualizer.tools import mqtt_recorder as mod

        out_file = tmp_path / "recording.jsonl"
        mock_paho = MagicMock()

        monkeypatch.setattr(sys, "argv", [
            "mqtt_recorder", "--scenario", "demo", "--output", str(out_file),
            "--stop-on", "__never__",
        ])

        state = {"calls": 0}

        def fake_sleep(_secs):
            state["calls"] += 1
            msg = MagicMock()
            msg.topic = "FloodSim/demo/events"
            msg.qos = 1
            msg.retain = False
            msg.payload = b"not json"
            mock_paho.on_message(mock_paho, None, msg)
            if state["calls"] >= 1:
                # Second call: send the stop message so main() can exit.
                stop_msg = MagicMock()
                stop_msg.topic = "FloodSim/demo/events"
                stop_msg.qos = 1
                stop_msg.retain = False
                stop_msg.payload = json.dumps({"process": "__never__"}).encode("utf-8")
                mock_paho.on_message(mock_paho, None, stop_msg)

        with patch("paho.mqtt.client.Client", return_value=mock_paho), \
             patch.object(mod.time, "sleep", side_effect=fake_sleep), \
             patch.object(mod.time, "monotonic", side_effect=[1.0, 2.0]):
            mod.main()

        lines = out_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["payload_raw"] == "not json"
