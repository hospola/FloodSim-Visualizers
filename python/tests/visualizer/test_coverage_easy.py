"""Tests to increase coverage on colors.py, types.py, registry.py and data_model gaps."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from python.visualizer.renderers.x3d.colors import X3DColorScheme, load_colors
from python.visualizer.renderers.registry import create_renderer, create_depth_provider


# ===========================================================================
# colors.py
# ===========================================================================

class TestX3DColorScheme:
    def test_default_state_colors(self) -> None:
        s = X3DColorScheme()
        assert len(s.state_colors) == 6

    def test_state_rgb_valid(self) -> None:
        s = X3DColorScheme()
        assert s.state_rgb(0) == s.state_colors[0]
        assert s.state_rgb(5) == s.state_colors[5]

    def test_state_rgb_clamps_low(self) -> None:
        s = X3DColorScheme()
        assert s.state_rgb(-1) == s.state_colors[0]

    def test_state_rgb_clamps_high(self) -> None:
        s = X3DColorScheme()
        assert s.state_rgb(99) == s.state_colors[-1]

    def test_palette_color_str(self) -> None:
        s = X3DColorScheme()
        result = s.palette_color_str()
        assert len(result.split("  ")) == 6


class TestLoadColors:
    def test_loads_x3d_section(self, tmp_path: Path) -> None:
        palette = {
            "x3d": {
                "sky_rgb": [0.1, 0.2, 0.3],
                "state_colors": [[float(i) / 10] * 3 for i in range(6)],
            }
        }
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        scheme = load_colors(p)
        assert scheme.sky == pytest.approx((0.1, 0.2, 0.3))
        assert len(scheme.state_colors) == 6

    def test_loads_x3d_section_default_sky(self, tmp_path: Path) -> None:
        palette = {"x3d": {"state_colors": [[0.1, 0.2, 0.3]] * 6}}
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        scheme = load_colors(p)
        assert scheme.sky == pytest.approx((0.53, 0.81, 0.98))

    def test_loads_x3d_no_state_colors_uses_defaults(self, tmp_path: Path) -> None:
        palette = {"x3d": {}}
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        scheme = load_colors(p)
        assert len(scheme.state_colors) == 6

    def test_loads_flood_risk_fallback(self, tmp_path: Path) -> None:
        palette = {
            "layers": {
                "flood_risk": [
                    {"value": i, "rgba": [i * 40, i * 20, i * 10, 255]}
                    for i in range(6)
                ]
            }
        }
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        scheme = load_colors(p)
        assert len(scheme.state_colors) == 6
        assert scheme.state_colors[1] == pytest.approx((40 / 255, 20 / 255, 10 / 255), abs=0.01)

    def test_returns_defaults_on_empty_json(self, tmp_path: Path) -> None:
        p = tmp_path / "palette.json"
        p.write_text("{}", encoding="utf-8")
        scheme = load_colors(p)
        assert len(scheme.state_colors) == 6

    def test_returns_defaults_on_missing_file(self, tmp_path: Path) -> None:
        scheme = load_colors(tmp_path / "missing.json")
        assert len(scheme.state_colors) == 6

    def test_returns_defaults_on_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        scheme = load_colors(p)
        assert len(scheme.state_colors) == 6


# ===========================================================================
# types.py
# ===========================================================================

class TestTypes:
    def _ctx(self):
        from python.visualizer.types import SpatialContext
        from pyproj import CRS
        from rasterio.transform import from_bounds
        crs = CRS.from_epsg(4326)
        transform = from_bounds(0, 0, 1, 1, 4, 3)
        return SpatialContext(crs=crs, transform=transform, width=4, height=3)

    def test_static_raster_nodata_float(self) -> None:
        from python.visualizer.types import StaticRaster
        ctx = self._ctx()
        data = np.zeros((3, 4), dtype=np.float32)
        r = StaticRaster(data=data, spatial_context=ctx)
        assert ctx.nodata_value == -9999.0

    def test_static_raster_nodata_int8(self) -> None:
        from python.visualizer.types import StaticRaster
        ctx = self._ctx()
        data = np.zeros((3, 4), dtype=np.int8)
        r = StaticRaster(data=data, spatial_context=ctx)
        assert ctx.nodata_value == -128.0

    def test_static_raster_coords_shape(self) -> None:
        from python.visualizer.types import StaticRaster
        ctx = self._ctx()
        data = np.zeros((3, 4), dtype=np.float32)
        r = StaticRaster(data=data, spatial_context=ctx)
        assert r.x_coords.shape == (4,)
        assert r.y_coords.shape == (3,)

    def test_static_raster_get_data_value(self) -> None:
        from python.visualizer.types import StaticRaster
        ctx = self._ctx()
        data = np.arange(12, dtype=np.float32).reshape(3, 4)
        r = StaticRaster(data=data, spatial_context=ctx)
        val = r.get_data_value(x=0.1, y=0.9)
        assert isinstance(val, float)

    def test_static_raster_get_data_value_out_of_bounds(self) -> None:
        from python.visualizer.types import StaticRaster
        ctx = self._ctx()
        data = np.zeros((3, 4), dtype=np.float32)
        r = StaticRaster(data=data, spatial_context=ctx)
        with pytest.raises(ValueError):
            r.get_data_value(x=99.0, y=99.0)

    def test_dynamic_raster_nodata_float(self) -> None:
        from python.visualizer.types import DynamicRaster
        ctx = self._ctx()
        data = np.zeros((2, 3, 4), dtype=np.float32)
        r = DynamicRaster(data=data, timestamps=[datetime.now(), datetime.now()],
                          downgrade_factor=1, spatial_context=ctx)
        assert ctx.nodata_value == -9999.0

    def test_dynamic_raster_nodata_int8(self) -> None:
        from python.visualizer.types import DynamicRaster
        ctx = self._ctx()
        data = np.zeros((2, 3, 4), dtype=np.int8)
        r = DynamicRaster(data=data, timestamps=[datetime.now(), datetime.now()],
                          downgrade_factor=1, spatial_context=ctx)
        assert ctx.nodata_value == -128.0


# ===========================================================================
# registry.py
# ===========================================================================

class TestRegistry:
    def test_create_renderer_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            create_renderer("nonexistent", "/tmp")

    def test_create_depth_provider_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            create_depth_provider("nonexistent")

    def test_create_renderer_csv(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.csv.csv_renderer import CSVRenderer
        r = create_renderer("csv", str(tmp_path))
        assert isinstance(r, CSVRenderer)

    def test_create_renderer_x3d(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer
        r = create_renderer("x3d", str(tmp_path))
        assert isinstance(r, X3DRenderer)

    def test_create_depth_provider_palette(self) -> None:
        from python.visualizer.depth_providers.palette import PaletteDepthProvider
        p = create_depth_provider("palette")
        assert isinstance(p, PaletteDepthProvider)

    def test_create_depth_provider_direct(self) -> None:
        from python.visualizer.depth_providers.direct import DirectDepthProvider
        p = create_depth_provider("direct")
        assert isinstance(p, DirectDepthProvider)


# ===========================================================================
# data_model.py — remaining gaps
# ===========================================================================

def _grid(size_x: int = 5, size_y: int = 4):
    from python.visualizer.data_model import SimulationGrid
    sim = SimulationGrid()
    sim.apply_init_map_config({
        "map": {"size_x": size_x, "size_y": size_y,
                "chunk_size": 1, "cell_resolution_m": 5.0}
    })
    return sim


class TestDataModelGaps:
    def test_apply_event_layer(self) -> None:
        sim = _grid()
        event = {"process": "EYE_SetState_Layer",
                 "changes": {"cells": {"0": {"state": "FLOODED"}}}}
        assert sim.apply_event(event) is True

    def test_apply_event_object(self) -> None:
        sim = _grid()
        event = {"process": "EYE_SetState",
                 "changes": {"coord": {"x": 1, "y": 1}, "state": "FLOODED"}}
        assert sim.apply_event(event) is True

    def test_apply_event_unknown_returns_false(self) -> None:
        sim = _grid()
        assert sim.apply_event({"process": "Unknown"}) is False

    def test_update_from_deltas_xor(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        sim.update_from_deltas([0, 1], [0, 0], step_index=0)
        assert sim.grid[0, 0] == 1
        assert sim.grid[0, 1] == 1
        assert sim.has_new_data is True

    def test_update_from_deltas_empty(self) -> None:
        sim = _grid()
        sim.update_from_deltas([], [], step_index=0)
        assert not sim.has_new_data

    def test_update_from_deltas_out_of_bounds(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        sim.update_from_deltas([99], [99], step_index=0)
        assert not sim.has_new_data

    def test_update_from_deltas_negative(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        sim.update_from_deltas([-1], [-1], step_index=0)
        assert not sim.has_new_data

    def test_init_agent_layer_shape_mismatch_crops(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "layer.csv"
        csv_path.write_text("0,1,2\n3,4,5\n6,7,8\n", encoding="utf-8")
        sim = _grid(size_x=2, size_y=2)
        event = {"id": "other", "data_path": str(tmp_path), "data_filename": "layer"}
        result = sim.apply_init_agent_layer(event)
        assert result is True
        assert sim.grid.shape == (2, 2)

    def test_terrain_layer_not_found_returns_false(self) -> None:
        sim = _grid()
        event = {"id": "topo_bathy", "data_path": "/nonexistent", "data_filename": "missing"}
        assert sim.apply_init_agent_layer(event) is False

    def test_collect_from_object_event_no_value_defaults_one(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"changes": {"coord": {"x": 1, "y": 1}}}
        result = sim.collect_from_object_event(event)
        assert result[0][2] == 1

    def test_update_from_layer_event_out_of_bounds_returns_false(self) -> None:
        sim = _grid(size_x=5, size_y=4)
        event = {"process": "EYE_SetState_Layer",
                 "changes": {"cells": {"9999": {"state": "FLOODED"}}}}
        assert sim.update_from_layer_event(event) is False
