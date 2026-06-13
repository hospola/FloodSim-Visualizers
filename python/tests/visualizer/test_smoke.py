"""Smoke / integration tests — no MQTT broker required.

Exercises the full pipeline from SimulationGrid through a real renderer to
disk output, verifying that the pieces fit together correctly.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from python.visualizer.data_model import SimulationGrid
from python.visualizer.renderers.base import FrameData, GridMeta
from python.visualizer.renderers.csv.csv_renderer import CSVRenderer
from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer
from python.visualizer.depth_providers.palette import PaletteDepthProvider


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _init_grid(size_x: int = 6, size_y: int = 4) -> SimulationGrid:
    sim = SimulationGrid()
    sim.apply_init_map_config({
        "map": {"size_x": size_x, "size_y": size_y, "cell_resolution_m": 5.0}
    })
    return sim


def _layer_event(flat_cells: dict) -> dict:
    """Build EYE_SetState_Layer with current protocol (flat-index dict keys)."""
    return {
        "process": "EYE_SetState_Layer",
        "changes": {"cells": flat_cells},
    }


def _apply_frame(sim: SimulationGrid, flat_cells: dict) -> list:
    pending = sim.collect_from_layer_event(_layer_event(flat_cells))
    sim.apply_bulk_changes(pending)
    return pending


# ===========================================================================
# Integration: SimulationGrid init sequence
# ===========================================================================

class TestInitSequence:
    def test_full_init_sequence(self, tmp_path: Path) -> None:
        """Handshake → InitMap_Config → InitAgent_Layer → Init_EOF."""
        npy = tmp_path / "terrain.npy"
        np.save(npy, np.linspace(0, 50, 24, dtype=np.float32))

        sim = _init_grid(size_x=6, size_y=4)
        assert sim.initialization["map_config_received"]
        assert sim.grid.shape == (4, 6)

        ok = sim.apply_init_agent_layer({
            "id": "topo_bathy",
            "data_path": str(tmp_path),
            "data_filename": "terrain",
        })
        assert ok
        assert sim.terrain_heights is not None
        assert sim.initialization["init_layers_received"] == 1

        sim.mark_init_agent_eof({})
        assert sim.initialization["init_agent_complete"]

        sim.mark_init_eof({"total_chunks_sent": 0})
        assert sim.initialization["init_complete"]

    def test_bulk_apply_then_consume(self) -> None:
        sim = _init_grid()
        _apply_frame(sim, {"0": {"state": "FLOODED"}, "7": {"state": "HIGH_DEPTH"}})
        assert sim.grid[0, 0] == 3   # FLOODED
        assert sim.grid[1, 1] == 4   # HIGH_DEPTH (7 // 6 = 1, 7 % 6 = 1)
        assert sim.has_new_data
        sim.consume_data()
        assert not sim.has_new_data


# ===========================================================================
# Integration: SimulationGrid → CSVRenderer → files
# ===========================================================================

class TestCSVPipeline:
    def test_full_csv_pipeline(self, tmp_path: Path) -> None:
        """Grid → CSVRenderer → meta.json + terrain.npy + step CSVs."""
        sim = _init_grid(size_x=6, size_y=4)
        terrain = np.linspace(0, 50, 24, dtype=np.float32)
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0, terrain_heights=terrain)

        renderer = CSVRenderer(str(tmp_path))
        renderer.setup(meta)

        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        # Frame 0: initial dry state
        depths = depth_provider.get_water_depths(sim.grid)
        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)

        # Frame 1: apply flood
        _apply_frame(sim, {"0": {"state": "FLOODED"}, "11": {"state": "EXTREME_DEPTH"}})
        depths = depth_provider.get_water_depths(sim.grid)
        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 1)

        renderer.close()

        csv_dir = tmp_path / "csv_data"
        assert (csv_dir / "meta.json").exists()
        assert (csv_dir / "terrain.npy").exists()
        assert (csv_dir / "step_00000.csv").exists()
        assert (csv_dir / "step_00001.csv").exists()

        meta_data = json.loads((csv_dir / "meta.json").read_text())
        assert meta_data["rows"] == 4
        assert meta_data["cols"] == 6

        step1 = (csv_dir / "step_00001.csv").read_text()
        assert "flood_risk" in step1
        assert "0,0,3" in step1  # row=0, col=0, state=FLOODED(3)

    def test_csv_sparse_only_wet_cells(self, tmp_path: Path) -> None:
        """Dry cells must not appear in the CSV."""
        sim = _init_grid(size_x=6, size_y=4)
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = CSVRenderer(str(tmp_path))
        renderer.setup(meta)
        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        # Only one wet cell
        _apply_frame(sim, {"3": {"state": "LOW_DEPTH"}})
        depths = depth_provider.get_water_depths(sim.grid)
        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)
        renderer.close()

        lines = [l for l in (tmp_path / "csv_data" / "step_00000.csv").read_text().splitlines()
                 if not l.startswith("#") and l and l != "row,col,flood_risk"]
        assert len(lines) == 1
        assert lines[0].endswith(",2")  # LOW_DEPTH = 2


# ===========================================================================
# Integration: SimulationGrid → X3DRenderer → player.html
# ===========================================================================

class TestX3DPipeline:
    def test_full_x3d_pipeline(self, tmp_path: Path) -> None:
        """Grid → X3DRenderer → player.html + manifest.json + flood PNGs."""
        sim = _init_grid(size_x=6, size_y=4)
        terrain = np.linspace(0, 50, 24, dtype=np.float32)
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0, terrain_heights=terrain)

        renderer = X3DRenderer(str(tmp_path))
        renderer.setup(meta)

        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        out_dir = tmp_path / "x3d_heightmap"
        assert (out_dir / "player.html").exists()
        manifest = json.loads((out_dir / "flood" / "manifest.json").read_text())
        assert manifest["live"] is True
        assert manifest["frames"] == []

        # Save two frames
        for step in range(2):
            _apply_frame(sim, {str(step): {"state": "FLOODED"}})
            depths = depth_provider.get_water_depths(sim.grid)
            renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), step)

        assert (out_dir / "flood" / "step_00000.png").exists()
        assert (out_dir / "flood" / "step_00001.png").exists()

        manifest = json.loads((out_dir / "flood" / "manifest.json").read_text())
        assert manifest["frames"] == ["step_00000", "step_00001"]
        assert manifest["live"] is True

        renderer.close()
        manifest = json.loads((out_dir / "flood" / "manifest.json").read_text())
        assert manifest["live"] is False

    def test_player_html_contains_config(self, tmp_path: Path) -> None:
        """player.html must embed __CONFIG__ with correct grid dimensions."""
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = X3DRenderer(str(tmp_path))
        renderer.setup(meta)

        html = (tmp_path / "x3d_heightmap" / "player.html").read_text()
        assert "__CONFIG__" in html
        assert '"mapW"' in html
        assert '"mapD"' in html


# ===========================================================================
# Integration: CSV → post-sim X3D player (run_viz x3d pipeline)
# ===========================================================================

class TestCSVToPlayerPipeline:
    def test_csv_to_player_end_to_end(self, tmp_path: Path) -> None:
        """CSVRenderer output → x3d_player generator → player.html."""
        # Step 1: simulate and write CSVs
        sim = _init_grid(size_x=6, size_y=4)
        terrain = np.linspace(0, 50, 24, dtype=np.float32)
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0, terrain_heights=terrain)

        csv_renderer = CSVRenderer(str(tmp_path))
        csv_renderer.setup(meta)
        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        _apply_frame(sim, {"0": {"state": "FLOODED"}, "5": {"state": "HIGH_DEPTH"}})
        depths = depth_provider.get_water_depths(sim.grid)
        csv_renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)
        csv_renderer.close()

        # Step 2: generate player from CSVs
        from python.visualizer.tools.x3d_player.generator import main as gen_main
        out = tmp_path / "player_out"
        rc = gen_main(["--csv", str(tmp_path / "csv_data"), "--output", str(out)])

        assert rc == 0
        assert (out / "player.html").exists()
        assert (out / "flood" / "step_00000.png").exists()
        assert (out / "js" / "app.js").exists()

        config_str = (out / "player.html").read_text()
        assert "step_00000" in config_str


# ===========================================================================
# Integration: error recovery
# ===========================================================================

class TestErrorRecovery:
    def test_malformed_cells_skipped_pipeline_continues(self, tmp_path: Path) -> None:
        """Malformed cell keys are skipped — the pipeline does not crash."""
        sim = _init_grid()
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = CSVRenderer(str(tmp_path))
        renderer.setup(meta)
        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        # Mix of valid and invalid keys
        event = {"process": "EYE_SetState_Layer", "changes": {"cells": {
            "bad_key": {"state": "FLOODED"},
            "0":       {"state": "FLOODED"},
            "":        {"state": "FLOODED"},
            "5":       {"state": "HIGH_DEPTH"},
        }}}
        pending = sim.collect_from_layer_event(event)
        sim.apply_bulk_changes(pending)

        depths = depth_provider.get_water_depths(sim.grid)
        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)
        renderer.close()

        # Valid cells applied, invalid ones silently skipped
        assert sim.grid[0, 0] == 3   # FLOODED
        assert sim.grid[0, 5] == 4   # HIGH_DEPTH
        csv = (tmp_path / "csv_data" / "step_00000.csv").read_text()
        assert "0,0,3" in csv

    def test_empty_frame_does_not_crash(self, tmp_path: Path) -> None:
        """A frame with no wet cells writes an empty CSV, no crash."""
        sim = _init_grid()
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = CSVRenderer(str(tmp_path))
        renderer.setup(meta)
        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        depths = depth_provider.get_water_depths(sim.grid)
        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)
        renderer.close()

        csv = (tmp_path / "csv_data" / "step_00000.csv").read_text()
        data_lines = [l for l in csv.splitlines()
                      if l and not l.startswith("#") and l != "row,col,flood_risk"]
        assert data_lines == []

    def test_out_of_bounds_cells_ignored(self) -> None:
        """Flat indices beyond grid size are silently ignored."""
        sim = _init_grid(size_x=5, size_y=4)
        event = {"process": "EYE_SetState_Layer", "changes": {"cells": {
            "9999999": {"state": "FLOODED"},  # way out of bounds
            "1":       {"state": "FLOODED"},  # valid
        }}}
        pending = sim.collect_from_layer_event(event)
        sim.apply_bulk_changes(pending)
        assert sim.grid[0, 1] == 3
        assert sim.grid.max() == 3  # only one cell changed


# ===========================================================================
# Integration: live manifest updates
# ===========================================================================

class TestLiveManifestUpdates:
    def test_manifest_updated_per_frame(self, tmp_path: Path) -> None:
        """manifest.json reflects new frames immediately after save_snapshot."""
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = X3DRenderer(str(tmp_path))
        renderer.setup(meta)
        manifest_path = tmp_path / "x3d_heightmap" / "flood" / "manifest.json"

        sim = _init_grid()
        depth_provider = PaletteDepthProvider()
        depth_provider.setup(4, 6)

        for step in range(3):
            _apply_frame(sim, {str(step): {"state": "FLOODED"}})
            depths = depth_provider.get_water_depths(sim.grid)
            renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), step)

            manifest = json.loads(manifest_path.read_text())
            assert len(manifest["frames"]) == step + 1
            assert manifest["frames"][step] == f"step_{step:05d}"
            assert manifest["live"] is True

        renderer.close()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["live"] is False
        assert len(manifest["frames"]) == 3

    def test_js_assets_present_immediately(self, tmp_path: Path) -> None:
        """JS modules are copied during setup, before any frame arrives."""
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = X3DRenderer(str(tmp_path))
        renderer.setup(meta)

        js_dir = tmp_path / "x3d_heightmap" / "js"
        assert js_dir.is_dir()
        assert (js_dir / "app.js").exists()
        assert (js_dir / "live.js").exists()


# ===========================================================================
# Integration: DirectDepthProvider with renderers
# ===========================================================================

class TestDirectDepthProvider:
    def test_csv_renderer_with_direct_provider(self, tmp_path: Path) -> None:
        """DirectDepthProvider feeds real float depths to CSVRenderer."""
        from python.visualizer.depth_providers.direct import DirectDepthProvider

        sim = _init_grid(size_x=6, size_y=4)
        meta = GridMeta(rows=4, cols=6, cell_size_m=5.0,
                        terrain_heights=np.zeros(24, dtype=np.float32))
        renderer = CSVRenderer(str(tmp_path))
        renderer.setup(meta)

        provider = DirectDepthProvider()
        provider.setup(4, 6)

        real_depths = np.zeros((4, 6), dtype=np.float32)
        real_depths[0, 0] = 1.5
        real_depths[1, 2] = 0.3
        provider.update_from_grid(real_depths)

        _apply_frame(sim, {"0": {"state": "FLOODED"}, "8": {"state": "LOW_DEPTH"}})
        depths = provider.get_water_depths(sim.grid)
        assert depths[0, 0] == pytest.approx(1.5)
        assert depths[1, 2] == pytest.approx(0.3)

        renderer.save_snapshot(FrameData(palette_grid=sim.grid, water_depths=depths), 0)
        renderer.close()
        assert (tmp_path / "csv_data" / "step_00000.csv").exists()


# ===========================================================================
# Integration: generate_x3d flat and LOD modes
# ===========================================================================

class TestGenerateX3dModes:
    def _csv_dir(self, tmp_path: Path) -> Path:
        import textwrap
        rows, cols = 4, 6
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "meta.json").write_text(
            json.dumps({"rows": rows, "cols": cols, "cell_size_m": 5.0}), encoding="utf-8"
        )
        np.save(tmp_path / "terrain.npy", np.linspace(0, 50, rows * cols, dtype=np.float32))
        (tmp_path / "step_00000.csv").write_text(
            textwrap.dedent("""\
                # rows=4 cols=6 cell_size_m=5.0
                row,col,flood_risk
                0,0,3
                1,2,5
            """), encoding="utf-8"
        )
        return tmp_path

    def test_flat_mode_produces_player_and_frame_html(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        csv = self._csv_dir(tmp_path / "csv")
        out = tmp_path / "out_flat"
        rc = main([str(csv), "--output", str(out), "--subsample", "1"])
        assert rc == 0
        assert (out / "player.html").exists()
        assert (out / "step_00000.html").exists()

    def test_flat_mode_player_contains_flood_data(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        csv = self._csv_dir(tmp_path / "csv")
        out = tmp_path / "out_flat"
        main([str(csv), "--output", str(out)])
        player = (out / "player.html").read_text()
        assert "simFrames" in player

    def test_lod_mode_produces_player(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        csv = self._csv_dir(tmp_path / "csv")
        out = tmp_path / "out_lod"
        rc = main([str(csv), "--output", str(out), "--lod",
                   "--lod-chunk", "2", "--lod-subsamples", "1,2"])
        assert rc == 0
        assert (out / "player.html").exists()
        player = (out / "player.html").read_text()
        assert "LOD" in player
