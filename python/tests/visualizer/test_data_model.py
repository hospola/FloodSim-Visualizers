"""Tests for data_model.py — SimulationGrid state management."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from python.visualizer.data_model import SimulationGrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grid(size_x: int = 5, size_y: int = 4) -> SimulationGrid:
    sim = SimulationGrid()
    sim.apply_init_map_config({
        "map": {"size_x": size_x, "size_y": size_y,
                "chunk_size": 1, "cell_resolution_m": 5.0}
    })
    return sim


def _layer_event(cells: dict) -> dict:
    return {"process": "EYE_SetState_Layer", "changes": {"cells": cells}}


# ---------------------------------------------------------------------------
# apply_init_map_config
# ---------------------------------------------------------------------------

class TestApplyInitMapConfig:
    def test_sets_grid_shape(self) -> None:
        sim = SimulationGrid()
        sim.apply_init_map_config({"map": {"size_x": 10, "size_y": 8, "cell_resolution_m": 5.0}})
        assert sim.grid.shape == (8, 10)

    def test_returns_true_on_success(self) -> None:
        sim = SimulationGrid()
        assert sim.apply_init_map_config({"map": {"size_x": 3, "size_y": 3}}) is True

    def test_returns_false_on_invalid_size(self) -> None:
        sim = SimulationGrid()
        assert sim.apply_init_map_config({"map": {"size_x": 0, "size_y": 5}}) is False
        assert sim.apply_init_map_config({"map": {"size_x": 5, "size_y": -1}}) is False

    def test_sets_map_config_received(self) -> None:
        sim = SimulationGrid()
        sim.apply_init_map_config({"map": {"size_x": 3, "size_y": 3}})
        assert sim.initialization["map_config_received"] is True

    def test_cell_size_m_property(self) -> None:
        sim = _grid()
        assert sim.cell_size_m == pytest.approx(5.0)

    def test_no_realloc_when_same_size(self) -> None:
        sim = SimulationGrid()
        sim.apply_init_map_config({"map": {"size_x": 5, "size_y": 4}})
        ref = sim.grid
        sim.apply_init_map_config({"map": {"size_x": 5, "size_y": 4}})
        assert sim.grid is ref  # same object, no realloc


# ---------------------------------------------------------------------------
# mark_init_agent_eof / mark_init_eof
# ---------------------------------------------------------------------------

class TestInitMarkers:
    def test_mark_init_agent_eof(self) -> None:
        sim = _grid()
        sim.mark_init_agent_eof({})
        assert sim.initialization["init_agent_complete"] is True

    def test_mark_init_eof(self) -> None:
        sim = _grid()
        sim.mark_init_eof({"total_chunks_sent": 10})
        assert sim.initialization["init_complete"] is True

    def test_mark_init_eof_without_chunks(self) -> None:
        sim = _grid()
        sim.mark_init_eof({})
        assert sim.initialization["init_complete"] is True


# ---------------------------------------------------------------------------
# collect_from_layer_event
# ---------------------------------------------------------------------------

class TestCollectFromLayerEvent:
    def test_returns_tuples(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        result = sim.collect_from_layer_event(_layer_event({"0": {"state": "FLOODED"}}))
        assert len(result) == 1
        row, col, val, height = result[0]
        assert row == 0 and col == 0
        assert val == 3  # FLOODED → palette 3

    def test_flat_index_to_row_col(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        # flat_index 7 → row=1, col=2 (7 // 5 = 1, 7 % 5 = 2)
        result = sim.collect_from_layer_event(_layer_event({"7": {"state": "HIGH_DEPTH"}}))
        row, col, val, _ = result[0]
        assert row == 1 and col == 2
        assert val == 4

    def test_height_captured(self) -> None:
        sim = _grid()
        result = sim.collect_from_layer_event(
            _layer_event({"0": {"state": "FLOODED", "height": 1.5}})
        )
        assert result[0][3] == pytest.approx(1.5)

    def test_empty_cells_returns_empty(self) -> None:
        sim = _grid()
        assert sim.collect_from_layer_event({"changes": {"cells": {}}}) == []

    def test_invalid_key_skipped(self) -> None:
        sim = _grid()
        result = sim.collect_from_layer_event(_layer_event({"bad_key": {"state": "FLOODED"}}))
        assert result == []

    def test_numeric_state(self) -> None:
        sim = _grid()
        result = sim.collect_from_layer_event(_layer_event({"0": {"state": 2}}))
        assert result[0][2] == 2


# ---------------------------------------------------------------------------
# collect_from_object_event
# ---------------------------------------------------------------------------

class TestCollectFromObjectEvent:
    def test_returns_single_tuple(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"changes": {"coord": {"x": 2, "y": 1}, "state": "FLOODED"}}
        result = sim.collect_from_object_event(event)
        assert len(result) == 1
        row, col, val = result[0]
        assert row == 1 and col == 2

    def test_missing_coord_returns_empty(self) -> None:
        sim = _grid()
        assert sim.collect_from_object_event({"changes": {}}) == []

    def test_out_of_bounds_returns_empty(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"changes": {"coord": {"x": 99, "y": 99}}}
        assert sim.collect_from_object_event(event) == []


# ---------------------------------------------------------------------------
# apply_bulk_changes / apply_bulk_float_changes
# ---------------------------------------------------------------------------

class TestApplyBulkChanges:
    def test_applies_palette_values(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        pending = [(0, 0, 3, 0.0), (1, 2, 5, 0.0)]
        sim.apply_bulk_changes(pending)
        assert sim.grid[0, 0] == 3
        assert sim.grid[1, 2] == 5

    def test_sets_has_new_data(self) -> None:
        sim = _grid()
        sim.apply_bulk_changes([(0, 0, 1, 0.0)])
        assert sim.has_new_data is True

    def test_empty_pending_returns_false(self) -> None:
        sim = _grid()
        assert sim.apply_bulk_changes([]) is False

    def test_apply_bulk_float_changes(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        pending = [(0, 0, 3, 1.5), (1, 2, 5, 0.3)]
        sim.apply_bulk_float_changes(pending)
        assert sim.water_depths_m[0, 0] == pytest.approx(1.5)
        assert sim.water_depths_m[1, 2] == pytest.approx(0.3)

    def test_bulk_float_skipped_if_no_height(self) -> None:
        sim = _grid()
        # tuples with only 3 elements — no height column
        sim.apply_bulk_float_changes([(0, 0, 1)])
        assert sim.water_depths_m[0, 0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# consume_data
# ---------------------------------------------------------------------------

class TestConsumeData:
    def test_resets_has_new_data(self) -> None:
        sim = _grid()
        sim.apply_bulk_changes([(0, 0, 1, 0.0)])
        assert sim.has_new_data is True
        sim.consume_data()
        assert sim.has_new_data is False

    def test_returns_grid(self) -> None:
        sim = _grid()
        result = sim.consume_data()
        assert result is sim.grid


# ---------------------------------------------------------------------------
# _resolve_cell_value
# ---------------------------------------------------------------------------

class TestResolveCellValue:
    def test_string_state(self) -> None:
        sim = _grid()
        assert sim._resolve_cell_value({"state": "FLOODED"}) == 3
        assert sim._resolve_cell_value({"state": "DRY"}) == 0
        assert sim._resolve_cell_value({"state": "HIGH_DEPTH"}) == 4

    def test_numeric_value(self) -> None:
        sim = _grid()
        assert sim._resolve_cell_value({"value": 2}) == 2

    def test_numeric_level(self) -> None:
        sim = _grid()
        assert sim._resolve_cell_value({"level": 5}) == 5

    def test_numeric_string(self) -> None:
        sim = _grid()
        assert sim._resolve_cell_value({"state": "3"}) == 3

    def test_unknown_state_defaults_to_1(self) -> None:
        sim = _grid()
        assert sim._resolve_cell_value({"state": "UNKNOWN_STATE"}) == 1


# ---------------------------------------------------------------------------
# _to_palette_levels
# ---------------------------------------------------------------------------

class TestToPaletteLevels:
    def test_already_palette_indices(self) -> None:
        sim = _grid()
        raw = np.array([[0, 1, 2], [3, 4, 5]], dtype=float)
        result = sim._to_palette_levels(raw)
        assert result.dtype == np.uint8
        np.testing.assert_array_equal(result, raw.astype(np.uint8))

    def test_normalizes_arbitrary_floats(self) -> None:
        sim = _grid()
        raw = np.array([0.0, 50.0, 100.0])
        result = sim._to_palette_levels(raw)
        assert result[0] == 0
        assert result[-1] == 5

    def test_all_nan_returns_zeros(self) -> None:
        sim = _grid()
        raw = np.array([np.nan, np.nan])
        result = sim._to_palette_levels(raw)
        assert (result == 0).all()

    def test_constant_array_returns_zeros(self) -> None:
        sim = _grid()
        raw = np.array([7.0, 7.0, 7.0])
        result = sim._to_palette_levels(raw)
        assert (result == 0).all()


# ---------------------------------------------------------------------------
# _load_raw_candidate / apply_init_agent_layer with file paths
# ---------------------------------------------------------------------------

class TestLoadFromFile:
    def test_load_npy_as_terrain(self, tmp_path: Path) -> None:
        data = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        npy_path = tmp_path / "terrain.npy"
        np.save(npy_path, data)

        sim = _grid(size_x=2, size_y=2)
        event = {
            "id": "topo_bathy",
            "data_path": str(tmp_path),
            "data_filename": "terrain",
        }
        result = sim.apply_init_agent_layer(event)
        assert result is True
        assert sim.terrain_heights is not None
        assert sim.terrain_heights.shape == (4,)

    def test_load_csv_layer(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "layer.csv"
        csv_path.write_text("0,1\n2,3\n", encoding="utf-8")

        sim = _grid(size_x=2, size_y=2)
        event = {
            "id": "other_layer",
            "data_path": str(tmp_path),
            "data_filename": "layer",
        }
        result = sim.apply_init_agent_layer(event)
        assert result is True

    def test_missing_fields_returns_false(self) -> None:
        sim = _grid()
        assert sim.apply_init_agent_layer({}) is False
        assert sim.apply_init_agent_layer({"id": "x"}) is False

    def test_nonexistent_path_returns_false(self) -> None:
        sim = _grid()
        event = {
            "id": "other",
            "data_path": "/nonexistent/path",
            "data_filename": "missing",
        }
        assert sim.apply_init_agent_layer(event) is False


# ---------------------------------------------------------------------------
# update_from_layer_event / update_from_object_event (legacy API)
# ---------------------------------------------------------------------------

class TestLegacyUpdateMethods:
    def test_update_from_layer_event(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = _layer_event({"2": {"state": "LOW_DEPTH"}})
        assert sim.update_from_layer_event(event) is True
        assert sim.grid[0, 2] == 2

    def test_update_from_layer_event_empty(self) -> None:
        sim = _grid()
        assert sim.update_from_layer_event({"changes": {"cells": {}}}) is False

    def test_update_from_object_event(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"changes": {"coord": {"x": 1, "y": 2}, "state": "FLOODED"}}
        assert sim.update_from_object_event(event) is True
        assert sim.grid[2, 1] == 3

    def test_update_from_object_event_no_coord(self) -> None:
        sim = _grid()
        assert sim.update_from_object_event({"changes": {}}) is False

    def test_update_from_object_event_out_of_bounds(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"changes": {"coord": {"x": 100, "y": 100}}}
        assert sim.update_from_object_event(event) is False


# ---------------------------------------------------------------------------
# apply_init_agent_layer — file-mode water depth
# ---------------------------------------------------------------------------

class TestFileInitWaterDepth:
    def test_populates_depths_and_palette(self, tmp_path: Path) -> None:
        # FLOOD_LEVELS default: {1: 0.001, 2: 0.1, 3: 0.3, 4: 1.0, 5: 2.0}
        depths = np.array([[0.0, 0.05], [0.5, 2.5]], dtype=np.float32)
        np.save(tmp_path / "water_depth.npy", depths)

        with patch("python.visualizer.data_model.config.INITIAL_STATE_SOURCE", "file"):
            sim = _grid(size_x=2, size_y=2)
            ok = sim.apply_init_agent_layer({
                "id": "water_depth",
                "data_path": str(tmp_path),
                "data_filename": "water_depth",
            })

        assert ok is True
        assert sim.water_depths_m[0, 1] == pytest.approx(0.05)
        assert sim.grid[0, 0] == 0  # 0.0  → dry
        assert sim.grid[0, 1] == 1  # 0.05 → very shallow  (0.001–0.1)
        assert sim.grid[1, 0] == 3  # 0.5  → medium depth  (0.3–1.0)
        assert sim.grid[1, 1] == 5  # 2.5  → extreme depth (≥ 2.0)

    def test_nodata_clamped_to_dry(self, tmp_path: Path) -> None:
        depths = np.array([[-9999.0, 1.0]], dtype=np.float32)
        np.save(tmp_path / "water_depth.npy", depths)

        with patch("python.visualizer.data_model.config.INITIAL_STATE_SOURCE", "file"):
            sim = _grid(size_x=2, size_y=1)
            sim.apply_init_agent_layer({
                "id": "water_depth",
                "data_path": str(tmp_path),
                "data_filename": "water_depth",
            })

        assert sim.water_depths_m[0, 0] == pytest.approx(0.0)
        assert sim.grid[0, 0] == 0  # nodata → dry

    def test_missing_file_returns_false(self) -> None:
        with patch("python.visualizer.data_model.config.INITIAL_STATE_SOURCE", "file"):
            sim = _grid(size_x=2, size_y=2)
            ok = sim.apply_init_agent_layer({
                "id": "water_depth",
                "data_path": "/nonexistent/path",
                "data_filename": "water_depth",
            })
        assert ok is False

    def test_mqtt_mode_does_not_touch_water_depths(self, tmp_path: Path) -> None:
        # In mqtt mode, water_depth layer goes through the normal palette path
        # and does NOT populate water_depths_m (that comes later via EYE_SetState_Layer)
        depths = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
        np.save(tmp_path / "water_depth.npy", depths)

        with patch("python.visualizer.data_model.config.INITIAL_STATE_SOURCE", "mqtt"):
            sim = _grid(size_x=2, size_y=2)
            ok = sim.apply_init_agent_layer({
                "id": "water_depth",
                "data_path": str(tmp_path),
                "data_filename": "water_depth",
            })

        assert ok is True
        assert (sim.water_depths_m == 0.0).all()
