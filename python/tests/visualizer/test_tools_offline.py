"""Tests for offline tools: demo, run_viz, idrisi_io, tile_utils."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ===========================================================================
# tile_utils — pure math, no I/O
# ===========================================================================

class TestTileUtils:
    def test_tile_bounds_origin(self) -> None:
        from python.visualizer.tools.tile_utils import tile_bounds_3857
        w, s, e, n = tile_bounds_3857(0, 0, 0)
        assert w == pytest.approx(-20037508.34, abs=1.0)
        assert e == pytest.approx(20037508.34, abs=1.0)
        assert s == pytest.approx(-20037508.34, abs=1.0)
        assert n == pytest.approx(20037508.34, abs=1.0)

    def test_tile_bounds_zoom1(self) -> None:
        from python.visualizer.tools.tile_utils import tile_bounds_3857
        w, s, e, n = tile_bounds_3857(1, 0, 0)
        assert e == pytest.approx(0.0, abs=1.0)
        assert s == pytest.approx(0.0, abs=1.0)

    def test_tiles_for_bbox_single(self) -> None:
        from python.visualizer.tools.tile_utils import tile_bounds_3857, tiles_for_bbox_3857
        w, s, e, n = tile_bounds_3857(5, 10, 12)
        tiles = list(tiles_for_bbox_3857(5, w + 1, s + 1, e - 1, n - 1))
        assert (10, 12) in tiles

    def test_tiles_for_bbox_covers_multiple(self) -> None:
        from python.visualizer.tools.tile_utils import tiles_for_bbox_3857, _HALF_CIRC
        tiles = list(tiles_for_bbox_3857(1, -_HALF_CIRC, -_HALF_CIRC, _HALF_CIRC, _HALF_CIRC))
        assert len(tiles) == 4  # 2×2 grid at zoom 1

    def test_encode_terrarium_sea_level(self) -> None:
        from python.visualizer.tools.tile_utils import encode_terrarium
        h = np.zeros((1, 1), dtype=np.float32)
        rgb = encode_terrarium(h)
        assert rgb.shape == (1, 1, 3)
        decoded = (int(rgb[0, 0, 0]) * 256 + int(rgb[0, 0, 1]) + int(rgb[0, 0, 2]) / 256.0) - 32768.0
        assert decoded == pytest.approx(0.0, abs=0.01)

    def test_encode_terrarium_positive(self) -> None:
        from python.visualizer.tools.tile_utils import encode_terrarium
        h = np.array([[100.0]], dtype=np.float32)
        rgb = encode_terrarium(h)
        decoded = (int(rgb[0, 0, 0]) * 256 + int(rgb[0, 0, 1]) + int(rgb[0, 0, 2]) / 256.0) - 32768.0
        assert decoded == pytest.approx(100.0, abs=0.1)

    def test_encode_flood_rgba_dry_transparent(self) -> None:
        from python.visualizer.tools.tile_utils import encode_flood_rgba
        colors = [(255, 0, 0)] * 6
        grid = np.zeros((2, 2), dtype=np.uint8)
        rgba = encode_flood_rgba(grid, colors)
        assert rgba.shape == (2, 2, 4)
        assert rgba[:, :, 3].max() == 0  # all transparent

    def test_encode_flood_rgba_wet_opaque(self) -> None:
        from python.visualizer.tools.tile_utils import encode_flood_rgba
        colors = [(i * 40, i * 20, i * 10) for i in range(6)]
        grid = np.array([[0, 3], [5, 1]], dtype=np.uint8)
        rgba = encode_flood_rgba(grid, colors)
        assert rgba[0, 0, 3] == 0    # dry → transparent
        assert rgba[0, 1, 3] == 200  # wet → opaque
        assert rgba[1, 0, 3] == 200


# ===========================================================================
# idrisi_io — read/write IDRISI format
# ===========================================================================

class TestIdrisiIO:
    def _spatial_ctx(self):
        from python.visualizer.types import SpatialContext
        from pyproj import CRS
        from rasterio.transform import from_bounds as fb
        crs = CRS.from_epsg(4326)
        transform = fb(0, 0, 1, 1, 3, 2)
        ctx = SpatialContext(crs=crs, transform=transform, width=3, height=2)
        ctx.nodata_value = -9999.0
        return ctx

    def test_save_and_read_real(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
        ctx = self._spatial_ctx()
        IdrisiIO.save(tmp_path, "test", data, ctx)
        assert (tmp_path / "test.doc").exists()
        assert (tmp_path / "test.img").exists()
        result = IdrisiIO.read(tmp_path, "test", read_metadata=True)
        np.testing.assert_array_almost_equal(result.data, data, decimal=4)

    def test_save_integer_dtype(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        data = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int32)
        ctx = self._spatial_ctx()
        IdrisiIO.save(tmp_path, "intdata", data, ctx)
        doc = (tmp_path / "intdata.doc").read_text()
        assert "integer" in doc

    def test_save_byte_dtype(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        data = np.array([[1, 2], [3, 4]], dtype=np.int8)
        ctx = self._spatial_ctx()
        IdrisiIO.save(tmp_path, "bytedata", data, ctx)
        doc = (tmp_path / "bytedata.doc").read_text()
        assert "byte" in doc

    def test_read_missing_img_raises(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        with pytest.raises(FileNotFoundError):
            IdrisiIO.read(tmp_path, "nonexistent", read_metadata=True)

    def test_read_missing_doc_raises(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        (tmp_path / "only.img").write_text("1 2\n3 4\n")
        with pytest.raises(FileNotFoundError):
            IdrisiIO.read(tmp_path, "only", read_metadata=True)

    def test_read_without_metadata_needs_context(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        (tmp_path / "data.img").write_text("1.0 2.0\n3.0 4.0\n")
        with pytest.raises(ValueError):
            IdrisiIO.read(tmp_path, "data", read_metadata=False, spatial_context=None)

    def test_read_without_metadata_with_context(self, tmp_path: Path) -> None:
        from python.visualizer.idrisi_io import IdrisiIO
        data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
        ctx = self._spatial_ctx()
        IdrisiIO.save(tmp_path, "ctx_test", data, ctx, save_metadata=False)
        result = IdrisiIO.read(tmp_path, "ctx_test", read_metadata=False, spatial_context=ctx)
        np.testing.assert_array_almost_equal(result.data, data, decimal=4)


# ===========================================================================
# demo.py — synthetic data generators
# ===========================================================================

class TestDemo:
    def test_make_terrain_shape(self) -> None:
        from python.visualizer.demo import _make_terrain
        t = _make_terrain(10, 12)
        assert t.shape == (10, 12)
        assert t.dtype == np.float32

    def test_make_terrain_center_lower(self) -> None:
        from python.visualizer.demo import _make_terrain
        t = _make_terrain(20, 20)
        assert t[10, 10] < t[0, 0]

    def test_make_flood_frame_shape(self) -> None:
        from python.visualizer.demo import _make_flood_frame
        g = _make_flood_frame(10, 12, frame=0, total_frames=5)
        assert g.shape == (10, 12)
        assert g.dtype == np.uint8

    def test_make_flood_frame_last_frame_most_flooded(self) -> None:
        from python.visualizer.demo import _make_flood_frame
        g_early = _make_flood_frame(20, 20, frame=0, total_frames=10)
        g_late  = _make_flood_frame(20, 20, frame=9, total_frames=10)
        assert (g_late > 0).sum() >= (g_early > 0).sum()

    def test_run_csv_renderer(self, tmp_path: Path) -> None:
        from python.visualizer.demo import run
        run("csv", str(tmp_path / "out"), rows=8, cols=8, cell_size_m=10.0, n_frames=2)
        assert (tmp_path / "out" / "csv_data" / "meta.json").exists()
        assert (tmp_path / "out" / "csv_data" / "step_00000.csv").exists()

    def test_run_x3d_renderer(self, tmp_path: Path) -> None:
        from python.visualizer.demo import run
        run("x3d", str(tmp_path / "out"), rows=8, cols=8, cell_size_m=10.0, n_frames=2)
        assert (tmp_path / "out" / "x3d_heightmap" / "player.html").exists()
        assert (tmp_path / "out" / "x3d_heightmap" / "flood" / "manifest.json").exists()


# ===========================================================================
# run_viz.py — orchestrator commands
# ===========================================================================

class TestRunViz:
    def _cfg(self, tmp_path: Path) -> dict:
        csv_dir = tmp_path / "csv_data"
        csv_dir.mkdir()
        (csv_dir / "meta.json").write_text(
            json.dumps({"rows": 4, "cols": 4, "cell_size_m": 5.0}), encoding="utf-8"
        )
        np.save(csv_dir / "terrain.npy", np.zeros(16, dtype=np.float32))
        (csv_dir / "step_00000.csv").write_text(
            "# rows=4 cols=4 cell_size_m=5.0\nrow,col,flood_risk\n1,1,3\n",
            encoding="utf-8",
        )
        return {
            "paths": {
                "idrisi":        "data/data_29_10_2024/topo_bathy",
                "csv_data":      str(csv_dir),
                "terrain_tiles": str(tmp_path / "terrain_tiles"),
                "flood_tiles":   str(tmp_path / "flood_tiles"),
                "x3d_heightmap": str(tmp_path / "x3d_heightmap"),
                "palette":       str(tmp_path / "palette.json"),
            },
            "x3d_heightmap": {"resolution": 5.0},
        }

    def test_run_x3d_command(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import run_x3d
        cfg = self._cfg(tmp_path)
        rc = run_x3d(cfg)
        assert rc == 0
        assert (tmp_path / "x3d_heightmap" / "player.html").exists()

    def test_main_x3d(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg):
            rc = main(["x3d"])
        assert rc == 0

    def test_main_all(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        mock_main = MagicMock(return_value=0)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             patch("python.visualizer.run_viz.run_terrain", return_value=0), \
             patch("python.visualizer.run_viz.run_flood", return_value=0), \
             patch("python.visualizer.run_viz.run_x3d", return_value=0):
            rc = main(["all"])
        assert rc == 0

    def test_main_unknown_command_exits(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             pytest.raises(SystemExit):
            main(["unknown_cmd"])

    def test_run_terrain_command(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import run_terrain
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.tools.generate_terrain_tiles.main", return_value=0) as mock_main:
            rc = run_terrain(cfg)
        assert rc == 0
        mock_main.assert_called_once()
        argv = mock_main.call_args[0][0]
        assert "--idrisi" in argv
        assert "--output" in argv

    def test_run_terrain_with_zoom_options(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import run_terrain
        cfg = self._cfg(tmp_path)
        cfg["terrain"] = {"min_zoom": 8, "max_zoom": 13}
        with patch("python.visualizer.tools.generate_terrain_tiles.main", return_value=0) as mock_main:
            run_terrain(cfg)
        argv = mock_main.call_args[0][0]
        assert "--min-zoom" in argv
        assert "--max-zoom" in argv

    def test_run_flood_command(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import run_flood
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.tools.generate_flood_tiles.main", return_value=0) as mock_main:
            rc = run_flood(cfg)
        assert rc == 0
        mock_main.assert_called_once()
        argv = mock_main.call_args[0][0]
        assert "--csv" in argv
        assert "--georef" in argv

    def test_main_terrain(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             patch("python.visualizer.run_viz.run_terrain", return_value=0) as mock_t:
            rc = main(["terrain"])
        assert rc == 0
        mock_t.assert_called_once()

    def test_main_flood(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             patch("python.visualizer.run_viz.run_flood", return_value=0) as mock_f:
            rc = main(["flood"])
        assert rc == 0
        mock_f.assert_called_once()

    def test_main_serve(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        cfg["server"] = {"port": 19999}
        mock_httpd = MagicMock()
        mock_httpd.__enter__ = MagicMock(return_value=mock_httpd)
        mock_httpd.__exit__ = MagicMock(return_value=False)
        mock_httpd.serve_forever.side_effect = KeyboardInterrupt
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             patch("http.server.HTTPServer", return_value=mock_httpd):
            try:
                rc = main(["serve"])
            except KeyboardInterrupt:
                rc = 0
        assert rc == 0

    def test_main_all_stops_on_failure(self, tmp_path: Path) -> None:
        from python.visualizer.run_viz import main
        cfg = self._cfg(tmp_path)
        with patch("python.visualizer.run_viz._load_config", return_value=cfg), \
             patch("python.visualizer.run_viz.run_terrain", return_value=1), \
             patch("python.visualizer.run_viz.run_flood", return_value=0) as mock_flood:
            rc = main(["all"])
        assert rc == 1
        mock_flood.assert_not_called()

    def test_load_config_reads_yml(self) -> None:
        from python.visualizer.run_viz import _load_config
        cfg = _load_config()
        assert "paths" in cfg
