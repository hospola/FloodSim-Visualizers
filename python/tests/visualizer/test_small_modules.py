"""Tests for small renderer and depth-provider modules."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from python.visualizer.depth_providers.direct import DirectDepthProvider
from python.visualizer.depth_providers.palette import PaletteDepthProvider
from python.visualizer.renderers.base import FrameData, GridMeta
from python.visualizer.renderers.csv.csv_renderer import CSVRenderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(rows: int = 4, cols: int = 5, cell_size: float = 5.0) -> GridMeta:
    terrain = np.zeros(rows * cols, dtype=np.float32)
    return GridMeta(rows=rows, cols=cols, cell_size_m=cell_size, terrain_heights=terrain)


def _make_frame(rows: int = 4, cols: int = 5) -> FrameData:
    grid = np.zeros((rows, cols), dtype=np.uint8)
    grid[1, 2] = 3
    grid[0, 0] = 1
    depths = np.zeros((rows, cols), dtype=np.float32)
    return FrameData(palette_grid=grid, water_depths=depths)


# ---------------------------------------------------------------------------
# CSVRenderer
# ---------------------------------------------------------------------------

class TestCSVRenderer:
    def test_setup_creates_files(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta())
        assert (tmp_path / "csv_data" / "meta.json").exists()
        assert (tmp_path / "csv_data" / "terrain.npy").exists()

    def test_setup_meta_content(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta(rows=4, cols=5, cell_size=10.0))
        meta = json.loads((tmp_path / "csv_data" / "meta.json").read_text())
        assert meta == {"rows": 4, "cols": 5, "cell_size_m": 10.0}

    def test_save_snapshot_writes_csv(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=0)
        csv_path = tmp_path / "csv_data" / "step_00000.csv"
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "row,col,flood_risk" in content
        assert "1,2,3" in content
        assert "0,0,1" in content

    def test_save_snapshot_only_wet_cells(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=0)
        lines = (tmp_path / "csv_data" / "step_00000.csv").read_text().splitlines()
        data_lines = [l for l in lines if not l.startswith("#") and l != "row,col,flood_risk"]
        assert len(data_lines) == 2  # only 2 wet cells

    def test_save_snapshot_step_index(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=42)
        assert (tmp_path / "csv_data" / "step_00042.csv").exists()

    def test_close_logs(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=0)
        r.close()  # should not raise

    def test_save_without_setup_raises(self, tmp_path: Path) -> None:
        r = CSVRenderer(str(tmp_path))
        with pytest.raises(RuntimeError):
            r.save_snapshot(_make_frame(), step_index=0)


# ---------------------------------------------------------------------------
# DirectDepthProvider
# ---------------------------------------------------------------------------

class TestDirectDepthProvider:
    def test_setup_initializes_zeros(self) -> None:
        p = DirectDepthProvider()
        p.setup(3, 4)
        depths = p.get_water_depths(np.zeros((3, 4), dtype=np.uint8))
        assert depths.shape == (3, 4)
        assert depths.dtype == np.float32
        assert not depths.any()

    def test_update_from_grid(self) -> None:
        p = DirectDepthProvider()
        p.setup(2, 2)
        new_depths = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        p.update_from_grid(new_depths)
        result = p.get_water_depths(np.zeros((2, 2), dtype=np.uint8))
        np.testing.assert_array_almost_equal(result, new_depths)

    def test_get_without_setup_raises(self) -> None:
        p = DirectDepthProvider()
        with pytest.raises(RuntimeError):
            p.get_water_depths(np.zeros((2, 2), dtype=np.uint8))


# ---------------------------------------------------------------------------
# PaletteDepthProvider
# ---------------------------------------------------------------------------

class TestPaletteDepthProvider:
    def test_setup_and_get(self) -> None:
        p = PaletteDepthProvider()
        p.setup(2, 2)
        grid = np.array([[0, 1], [3, 5]], dtype=np.uint8)
        depths = p.get_water_depths(grid)
        assert depths.shape == (2, 2)
        assert depths[0, 0] == pytest.approx(0.0)   # dry
        assert depths[1, 1] > depths[1, 0]           # state 5 deeper than 3


# ---------------------------------------------------------------------------
# MatplotlibRenderer
# ---------------------------------------------------------------------------

class TestMatplotlibRenderer:
    def test_setup_creates_visualizer(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.matplotlib_renderer import MatplotlibRenderer
        from python.visualizer.visualizer import GridVisualizer

        with patch.object(GridVisualizer, "__init__", lambda self, **kw: None):
            r = MatplotlibRenderer(str(tmp_path))
            r.setup(_make_meta())
            assert r._visualizer is not None

    def test_save_without_setup_raises(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.matplotlib_renderer import MatplotlibRenderer

        r = MatplotlibRenderer(str(tmp_path))
        with pytest.raises(RuntimeError):
            r.save_snapshot(_make_frame(), step_index=0)

    def test_close_without_setup_is_safe(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.matplotlib_renderer import MatplotlibRenderer

        r = MatplotlibRenderer(str(tmp_path))
        r.close()  # should not raise


# ---------------------------------------------------------------------------
# X3DRenderer
# ---------------------------------------------------------------------------

class TestX3DRenderer:
    def test_setup_creates_player_and_manifest(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer

        r = X3DRenderer(str(tmp_path))
        r.setup(_make_meta())
        assert (tmp_path / "x3d_heightmap" / "player.html").exists()
        assert (tmp_path / "x3d_heightmap" / "flood" / "manifest.json").exists()
        assert (tmp_path / "x3d_heightmap" / "js").is_dir()

    def test_manifest_starts_live(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer
        import json

        r = X3DRenderer(str(tmp_path))
        r.setup(_make_meta())
        manifest = json.loads(
            (tmp_path / "x3d_heightmap" / "flood" / "manifest.json").read_text()
        )
        assert manifest["live"] is True
        assert manifest["frames"] == []

    def test_save_snapshot_writes_png_and_updates_manifest(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer
        import json

        r = X3DRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=0)

        assert (tmp_path / "x3d_heightmap" / "flood" / "step_00000.png").exists()
        manifest = json.loads(
            (tmp_path / "x3d_heightmap" / "flood" / "manifest.json").read_text()
        )
        assert manifest["frames"] == ["step_00000"]
        assert manifest["live"] is True

    def test_close_marks_manifest_done(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer
        import json

        r = X3DRenderer(str(tmp_path))
        r.setup(_make_meta())
        r.save_snapshot(_make_frame(), step_index=0)
        r.close()

        manifest = json.loads(
            (tmp_path / "x3d_heightmap" / "flood" / "manifest.json").read_text()
        )
        assert manifest["live"] is False

    def test_save_without_setup_raises(self, tmp_path: Path) -> None:
        from python.visualizer.renderers.x3d.x3d_renderer import X3DRenderer

        r = X3DRenderer(str(tmp_path))
        with pytest.raises(RuntimeError):
            r.save_snapshot(_make_frame(), step_index=0)
