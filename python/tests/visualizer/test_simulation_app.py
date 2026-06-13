"""Unit tests for SimulationApp — the application core.

All tests call handle_event() / on_idle() directly; no threads or MQTT needed.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from python.visualizer import config
from python.visualizer.simulation_app import SimulationApp
from python.visualizer.depth_providers.palette import PaletteDepthProvider
from python.visualizer.renderers.base import BaseRenderer


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_app(renderer=None) -> SimulationApp:
    if renderer is None:
        renderer = MagicMock(spec=BaseRenderer)
    return SimulationApp(renderer, PaletteDepthProvider(), MagicMock())


def _init(app: SimulationApp, size_x: int = 5, size_y: int = 4) -> None:
    app.handle_event({"process": "InitMap_Config",
                      "map": {"size_x": size_x, "size_y": size_y, "cell_resolution_m": 1.0}})
    app.handle_event({"process": "Init_EOF", "total_chunks_sent": 0})


# ===========================================================================
# Init sequence
# ===========================================================================

class TestInitSequence:
    def test_init_map_config_resizes_grid(self) -> None:
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 10, "size_y": 8, "cell_resolution_m": 5.0}})
        assert app._simulation.grid.shape == (8, 10)

    def test_init_map_config_invalid_skips_setup(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 0, "size_y": 0}})
        renderer.setup.assert_not_called()

    def test_init_eof_calls_renderer_setup(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        _init(app, size_x=5, size_y=4)
        renderer.setup.assert_called_once()
        meta = renderer.setup.call_args[0][0]
        assert meta.rows == 4
        assert meta.cols == 5

    def test_init_eof_renders_initial_snapshot(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        with patch("python.visualizer.simulation_app.config.RENDER_ON_INIT_EOF", True):
            _init(app)
        renderer.save_snapshot.assert_called_once()
        assert app._step_index == 1

    def test_init_eof_no_snapshot_when_flag_off(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        with patch("python.visualizer.simulation_app.config.RENDER_ON_INIT_EOF", False):
            _init(app)
        renderer.save_snapshot.assert_not_called()
        assert app._step_index == 0

    def test_init_agent_eof_marks_complete(self) -> None:
        app = _make_app()
        app.handle_event({"process": "InitAgent_EOF"})
        assert app._simulation.initialization["init_agent_complete"]

    def test_init_agent_layer_ok(self, tmp_path) -> None:
        npy = tmp_path / "layer.npy"
        np.save(npy, np.zeros((4, 5), dtype=np.float32))
        app = _make_app()
        _init(app)
        app.handle_event({"process": "InitAgent_Layer",
                          "id": "topo_bathy",
                          "data_path": str(tmp_path),
                          "data_filename": "layer"})
        assert app._simulation.terrain_heights is not None

    def test_init_agent_layer_fail_does_not_raise(self) -> None:
        app = _make_app()
        _init(app)
        app.handle_event({"process": "InitAgent_Layer",
                          "id": "topo_bathy",
                          "data_path": "/nonexistent",
                          "data_filename": "missing"})


# ===========================================================================
# Frame flow
# ===========================================================================

class TestFrameFlow:
    def test_frame_start_clears_pending_and_sets_time(self) -> None:
        app = _make_app()
        _init(app)
        app._pending_changes = [(0, 0, 1, 0.0)]
        app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
        assert app._pending_changes == []
        assert app._frame_start_time is not None

    def test_eye_setstate_layer_extends_pending(self) -> None:
        app = _make_app()
        _init(app)
        app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
        app.handle_event({"process": "EYE_SetState_Layer",
                          "changes": {"cells": {"0": {"state": "FLOODED"}}}})
        assert len(app._pending_changes) == 1

    def test_eye_setstate_layer_publishes_ack_when_batch_full(self) -> None:
        app = _make_app()
        _init(app)
        app.handle_event({"process": "FrameStart", "total_chunks": 2, "chunks_per_batch": 1})
        app.handle_event({"process": "EYE_SetState_Layer",
                          "changes": {"cells": {"0": {"state": "FLOODED"}}}})
        app._control.publish_chunk_ack.assert_called_once()

    def test_eye_setstate_object_extends_pending(self) -> None:
        app = _make_app()
        _init(app)
        app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
        app.handle_event({"process": "EYE_SetState",
                          "changes": {"coord": {"x": 1, "y": 1}, "state": "FLOODED"}})
        assert len(app._pending_changes) == 1

    def test_frame_end_applies_changes_and_clears_state(self) -> None:
        app = _make_app()
        _init(app)
        app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
        app.handle_event({"process": "EYE_SetState_Layer",
                          "changes": {"cells": {"0": {"state": "FLOODED"}}}})
        app.handle_event({"process": "FrameEnd"})
        assert app._pending_changes == []
        assert app._frame_start_time is None
        assert app._simulation.grid[0, 0] != 0

    def test_eye_frame_sync_saves_snapshot(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        _init(app)
        init_calls = renderer.save_snapshot.call_count
        app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
        app.handle_event({"process": "EYE_SetState_Layer",
                          "changes": {"cells": {"0": {"state": "FLOODED"}}}})
        app.handle_event({"process": "FrameEnd"})
        app.handle_event({"process": "EYE_Frame_Sync", "simulation_time": "t0"})
        assert renderer.save_snapshot.call_count == init_calls + 1

    def test_eye_frame_sync_skips_when_no_new_data(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        _init(app)
        init_calls = renderer.save_snapshot.call_count
        # No FrameStart/FrameEnd → has_new_data is False
        app.handle_event({"process": "EYE_Frame_Sync", "simulation_time": "t0"})
        assert renderer.save_snapshot.call_count == init_calls

    def test_sim_end_sets_running_false(self) -> None:
        app = _make_app()
        assert app._running is True
        app.handle_event({"process": "Sim_End"})
        assert app._running is False

    def test_system_disconnected_does_not_raise(self) -> None:
        app = _make_app()
        app.handle_event({"process": "System_Disconnected"})

    def test_unknown_event_does_not_raise(self) -> None:
        app = _make_app()
        app.handle_event({"process": "UnknownXYZ_event"})


# ===========================================================================
# Frame timeout (on_idle)
# ===========================================================================

class TestFrameTimeout:
    def test_on_idle_discards_pending_after_timeout(self) -> None:
        app = _make_app()
        app._frame_start_time = time.monotonic() - (config.FRAME_TIMEOUT_SECONDS + 1)
        app._pending_changes = [(0, 0, 1, 0.0)]
        app.on_idle()
        assert app._pending_changes == []
        assert app._frame_start_time is None

    def test_on_idle_resets_chunk_counters_after_timeout(self) -> None:
        app = _make_app()
        app._frame_start_time = time.monotonic() - (config.FRAME_TIMEOUT_SECONDS + 1)
        app._chunks_per_batch = 5
        app._chunks_since_ack = 3
        app.on_idle()
        assert app._chunks_per_batch == 0
        assert app._chunks_since_ack == 0

    def test_on_idle_does_nothing_when_no_frame_in_progress(self) -> None:
        app = _make_app()
        app._frame_start_time = None
        app._pending_changes = [(0, 0, 1, 0.0)]
        app.on_idle()
        assert app._pending_changes == [(0, 0, 1, 0.0)]

    def test_on_idle_does_nothing_when_not_yet_timed_out(self) -> None:
        app = _make_app()
        app._frame_start_time = time.monotonic()
        app._pending_changes = [(0, 0, 1, 0.0)]
        app.on_idle()
        assert app._pending_changes == [(0, 0, 1, 0.0)]


# ===========================================================================
# close
# ===========================================================================

class TestClose:
    def test_close_delegates_to_renderer(self) -> None:
        renderer = MagicMock(spec=BaseRenderer)
        app = _make_app(renderer)
        app.close()
        renderer.close.assert_called_once()


# ===========================================================================
# File-mode initial state guard
# ===========================================================================

class TestFileModeGuard:
    def test_eye_set_state_layer_ignored_before_init_eof(self) -> None:
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 5, "size_y": 4, "cell_resolution_m": 1.0}})
        with patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "file"):
            app.handle_event({"process": "EYE_SetState_Layer",
                              "changes": {"cells": {"0": {"state": "FLOODED", "height": 1.5}}}})
        assert app._pending_changes == []

    def test_eye_set_state_ignored_before_init_eof(self) -> None:
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 5, "size_y": 4, "cell_resolution_m": 1.0}})
        with patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "file"):
            app.handle_event({"process": "EYE_SetState",
                              "changes": {"coord": {"x": 1, "y": 1}, "state": "FLOODED"}})
        assert app._pending_changes == []

    def test_eye_set_state_layer_collected_after_init_eof(self) -> None:
        app = _make_app()
        _init(app, size_x=5, size_y=4)  # sets init_complete = True
        with patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "file"):
            app.handle_event({"process": "FrameStart", "total_chunks": 1, "chunks_per_batch": 0})
            app.handle_event({"process": "EYE_SetState_Layer",
                              "changes": {"cells": {"0": {"state": "FLOODED", "height": 1.5}}}})
        assert len(app._pending_changes) == 1

    def test_mqtt_mode_collects_before_init_eof(self) -> None:
        # In mqtt mode the guard is inactive — messages before Init_EOF go into pending_changes
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 5, "size_y": 4, "cell_resolution_m": 1.0}})
        with patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "mqtt"):
            app.handle_event({"process": "EYE_SetState_Layer",
                              "changes": {"cells": {"0": {"state": "FLOODED", "height": 1.5}}}})
        assert len(app._pending_changes) == 1

    def test_init_agent_eof_triggers_file_load(self, tmp_path) -> None:
        depths = np.array([[0.0, 1.5], [2.5, 0.0]], dtype=np.float32)
        np.save(tmp_path / "water_depth.npy", depths)
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 2, "size_y": 2, "cell_resolution_m": 5.0}})
        with (
            patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "file"),
            patch("python.visualizer.simulation_app.config.WATER_DEPTH_DATA_PATH", str(tmp_path)),
            patch("python.visualizer.simulation_app.config.WATER_DEPTH_DATA_FILENAME", "water_depth"),
        ):
            app.handle_event({"process": "InitAgent_EOF"})
        assert app._simulation.water_depths_m[0, 1] == pytest.approx(1.5)
        assert app._simulation.grid[0, 1] != 0  # not dry

    def test_init_agent_eof_no_file_load_in_mqtt_mode(self) -> None:
        app = _make_app()
        app.handle_event({"process": "InitMap_Config",
                          "map": {"size_x": 5, "size_y": 4, "cell_resolution_m": 1.0}})
        with patch("python.visualizer.simulation_app.config.INITIAL_STATE_SOURCE", "mqtt"):
            app.handle_event({"process": "InitAgent_EOF"})
        # grid untouched — all dry
        assert (app._simulation.grid == 0).all()


# ===========================================================================
# main() wiring
# ===========================================================================

class TestMain:
    def test_main_normal_flow(self) -> None:
        from python.visualizer.main import main

        with (
            patch("python.visualizer.main.create_renderer"),
            patch("python.visualizer.main.create_depth_provider"),
            patch("python.visualizer.main.SimulationApp") as mock_app_cls,
            patch("python.visualizer.main.MQTTMonitorClient") as mock_client_cls,
            patch("sys.exit"),
        ):
            mock_app = mock_app_cls.return_value
            mock_client = mock_client_cls.return_value
            main()

        mock_client.connect.assert_called_once()
        mock_client.run.assert_called_once()
        mock_app.close.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_main_keyboard_interrupt(self) -> None:
        from python.visualizer.main import main

        with (
            patch("python.visualizer.main.create_renderer"),
            patch("python.visualizer.main.create_depth_provider"),
            patch("python.visualizer.main.SimulationApp") as mock_app_cls,
            patch("python.visualizer.main.MQTTMonitorClient") as mock_client_cls,
            patch("sys.exit"),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.run.side_effect = KeyboardInterrupt()
            mock_app = mock_app_cls.return_value
            main()

        mock_app.close.assert_called_once()
        mock_client.disconnect.assert_called_once()
