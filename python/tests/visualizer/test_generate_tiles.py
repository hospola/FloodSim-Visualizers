"""Tests for the generate_flood_tiles and generate_terrain_tiles CLI tools."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


# ===========================================================================
# generate_flood_tiles
# ===========================================================================

class TestLoadStateColors:
    def test_no_palette_path_returns_defaults(self) -> None:
        from python.visualizer.tools.generate_flood_tiles import _load_state_colors
        colors = _load_state_colors(None)
        assert len(colors) == 6
        assert colors[0] == (245, 222, 179)

    def test_missing_palette_file_returns_defaults(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _load_state_colors
        colors = _load_state_colors(tmp_path / "missing.json")
        assert colors[0] == (245, 222, 179)

    def test_flood_risk_layer_takes_priority(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _load_state_colors
        palette_path = tmp_path / "color_palette.json"
        palette_path.write_text(json.dumps({
            "layers": {
                "flood_risk": [
                    {"value": 1, "rgba": [10, 20, 30, 255]},
                    {"value": 0, "rgba": [40, 50, 60, 255]},
                ]
            }
        }), encoding="utf-8")
        colors = _load_state_colors(palette_path)
        assert colors[0] == (40, 50, 60)
        assert colors[1] == (10, 20, 30)

    def test_x3d_state_colors_used_when_no_flood_risk(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _load_state_colors
        palette_path = tmp_path / "color_palette.json"
        palette_path.write_text(json.dumps({
            "x3d": {"state_colors": [[0.1, 0.2, 0.3], [1.0, 1.0, 1.0]]}
        }), encoding="utf-8")
        colors = _load_state_colors(palette_path)
        assert colors[0] == (25, 51, 76)
        assert colors[1] == (255, 255, 255)

    def test_invalid_json_returns_defaults(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _load_state_colors
        palette_path = tmp_path / "color_palette.json"
        palette_path.write_text("not json", encoding="utf-8")
        colors = _load_state_colors(palette_path)
        assert colors[0] == (245, 222, 179)


class TestAutoDetectPalette:
    def test_finds_palette_in_ancestor(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _auto_detect_palette
        palette_dir = tmp_path / "data" / "data_29_10_2024"
        palette_dir.mkdir(parents=True)
        palette_path = palette_dir / "color_palette.json"
        palette_path.write_text("{}", encoding="utf-8")

        csv_dir = tmp_path / "outputs" / "csv_data"
        csv_dir.mkdir(parents=True)

        assert _auto_detect_palette(csv_dir) == palette_path

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import _auto_detect_palette
        csv_dir = tmp_path / "outputs" / "csv_data"
        csv_dir.mkdir(parents=True)

        assert _auto_detect_palette(csv_dir) is None


class TestGenerateFloodTilesMain:
    def _write_csv_data(self, csv_dir: Path, rows: int, cols: int) -> None:
        csv_dir.mkdir(parents=True, exist_ok=True)
        (csv_dir / "meta.json").write_text(
            json.dumps({"rows": rows, "cols": cols, "cell_size_m": 5.0}), encoding="utf-8"
        )
        lines = ["# rows=%d cols=%d cell_size_m=5.0" % (rows, cols), "row,col,flood_risk"]
        for r in range(rows):
            for c in range(cols):
                lines.append(f"{r},{c},3")
        (csv_dir / "step_00000.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_georef(self, georef_path: Path, z: int, x: int, y: int) -> None:
        from python.visualizer.tools.tile_utils import tile_bounds_3857
        west, south, east, north = tile_bounds_3857(z, x, y)
        georef_path.parent.mkdir(parents=True, exist_ok=True)
        georef_path.write_text(json.dumps({
            "xll": west, "yll": south, "xur": east, "yur": north,
            "rows": 4, "cols": 4,
            "crs_epsg": 3857,
            "min_zoom": z, "max_zoom": z,
            "dom_west_3857": west, "dom_south_3857": south,
            "dom_east_3857": east, "dom_north_3857": north,
        }), encoding="utf-8")

    def test_full_run_writes_tiles_and_manifest(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import main

        csv_dir = tmp_path / "csv_data"
        self._write_csv_data(csv_dir, rows=4, cols=4)

        georef_path = tmp_path / "terrain" / "georef.json"
        self._write_georef(georef_path, z=12, x=2048, y=2048)

        output_dir = tmp_path / "flood"

        rc = main([
            "--csv", str(csv_dir),
            "--georef", str(georef_path),
            "--output", str(output_dir),
        ])

        assert rc == 0
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["frames"] == [{"index": 0, "file": "step_00000"}]
        assert manifest["min_zoom"] == 12
        assert manifest["max_zoom"] == 12

        tile_path = output_dir / "step_00000" / "12" / "2048" / "2048.png"
        assert tile_path.exists()

    def test_frames_limit_and_max_zoom_override(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import main

        csv_dir = tmp_path / "csv_data"
        self._write_csv_data(csv_dir, rows=4, cols=4)
        # second frame
        (csv_dir / "step_00001.csv").write_text(
            (csv_dir / "step_00000.csv").read_text(encoding="utf-8"), encoding="utf-8"
        )

        georef_path = tmp_path / "terrain" / "georef.json"
        self._write_georef(georef_path, z=12, x=2048, y=2048)

        output_dir = tmp_path / "flood"

        rc = main([
            "--csv", str(csv_dir),
            "--georef", str(georef_path),
            "--output", str(output_dir),
            "--max-zoom", "12",
            "--frames", "1",
        ])

        assert rc == 0
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["frames"] == [{"index": 0, "file": "step_00000"}]

    def test_invalid_zoom_range_returns_error(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import main

        csv_dir = tmp_path / "csv_data"
        self._write_csv_data(csv_dir, rows=4, cols=4)

        georef_path = tmp_path / "terrain" / "georef.json"
        georef_path.parent.mkdir(parents=True, exist_ok=True)
        georef_path.write_text(json.dumps({
            "xll": 0, "yll": 0, "xur": 1, "yur": 1,
            "crs_epsg": 3857,
            "min_zoom": 5, "max_zoom": 2,
            "dom_west_3857": 0, "dom_south_3857": 0,
            "dom_east_3857": 1, "dom_north_3857": 1,
        }), encoding="utf-8")

        rc = main([
            "--csv", str(csv_dir),
            "--georef", str(georef_path),
            "--output", str(tmp_path / "flood"),
        ])

        assert rc == 1

    def test_no_frames_returns_error(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_flood_tiles import main

        csv_dir = tmp_path / "csv_data"
        csv_dir.mkdir(parents=True)
        (csv_dir / "meta.json").write_text(json.dumps({"rows": 4, "cols": 4}), encoding="utf-8")

        georef_path = tmp_path / "terrain" / "georef.json"
        self._write_georef(georef_path, z=12, x=2048, y=2048)

        rc = main([
            "--csv", str(csv_dir),
            "--georef", str(georef_path),
            "--output", str(tmp_path / "flood"),
        ])

        assert rc == 1


# ===========================================================================
# generate_terrain_tiles
# ===========================================================================

class TestHillshadeAndColormap:
    def test_hillshade_flat_terrain_is_uniform(self) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _hillshade
        heights = np.full((4, 4), 10.0, dtype=np.float32)
        shade = _hillshade(heights)
        assert shade.shape == (4, 4)
        assert np.allclose(shade, shade[0, 0])

    def test_encode_colormap_shape_and_range(self) -> None:
        from python.visualizer.tools.generate_terrain_tiles import encode_colormap
        heights = np.array([[-20, -5], [50, 500]], dtype=np.float32)
        rgb = encode_colormap(heights)
        assert rgb.shape == (2, 2, 3)
        assert rgb.dtype == np.uint8


class TestReadDocAndBbox:
    def _write_doc(self, path: Path, **overrides) -> None:
        fields = {
            "columns": "4",
            "rows": "4",
            "min. X": "0",
            "max. X": "100",
            "min. Y": "0",
            "max. Y": "100",
            "resolution": "25",
            "ref. system": "EPSG:3857",
        }
        fields.update(overrides)
        content = "\n".join(f"{k}: {v}" for k, v in fields.items())
        path.write_text(content, encoding="utf-8")

    def test_read_doc_parses_fields(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _read_doc
        self._write_doc(tmp_path / "topo_bathy.doc")

        doc = _read_doc(tmp_path)

        assert doc["cols"] == 4
        assert doc["rows"] == 4
        assert doc["min_x"] == 0.0
        assert doc["max_x"] == 100.0
        assert doc["cell_size"] == 25.0
        assert doc["crs_str"] == "EPSG:3857"

    def test_bbox_3857_identity_for_epsg3857(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _read_doc, _bbox_3857
        self._write_doc(tmp_path / "topo_bathy.doc")
        doc = _read_doc(tmp_path)

        west, south, east, north = _bbox_3857(doc)

        assert west == pytest.approx(0.0)
        assert south == pytest.approx(0.0)
        assert east == pytest.approx(100.0)
        assert north == pytest.approx(100.0)


class TestLoadHeights:
    def test_load_heights_from_npy(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _load_heights
        data = np.arange(16, dtype=np.float32)
        npy_path = tmp_path / "terrain.npy"
        np.save(npy_path, data)

        heights = _load_heights(tmp_path, "topo_bathy", npy_path, rows=4, cols=4)

        assert heights.shape == (4, 4)
        assert heights[0, 0] == 0.0

    def test_load_heights_replaces_nodata(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _load_heights
        data = np.full(16, -9999.0, dtype=np.float32)
        data[0] = 42.0
        npy_path = tmp_path / "terrain.npy"
        np.save(npy_path, data)

        heights = _load_heights(tmp_path, "topo_bathy", npy_path, rows=4, cols=4)

        assert heights[0, 0] == 42.0
        assert heights[0, 1] == 0.0

    def test_load_heights_from_img(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import _load_heights
        rows = "\n".join(" ".join("1.0" for _ in range(4)) for _ in range(4))
        (tmp_path / "topo_bathy.img").write_text(rows, encoding="utf-8")

        heights = _load_heights(tmp_path, "topo_bathy", None, rows=4, cols=4)

        assert heights.shape == (4, 4)
        assert heights[0, 0] == 1.0


class TestGenerateTerrainTilesMain:
    def _write_inputs(self, tmp_path: Path, z: int, x: int, y: int) -> tuple[Path, Path]:
        from python.visualizer.tools.tile_utils import tile_bounds_3857
        west, south, east, north = tile_bounds_3857(z, x, y)

        idrisi_dir = tmp_path / "topo_bathy"
        idrisi_dir.mkdir(parents=True)
        doc_content = "\n".join([
            "columns: 4",
            "rows: 4",
            f"min. X: {west}",
            f"max. X: {east}",
            f"min. Y: {south}",
            f"max. Y: {north}",
            "resolution: 25",
            "ref. system: EPSG:3857",
        ])
        (idrisi_dir / "topo_bathy.doc").write_text(doc_content, encoding="utf-8")

        npy_path = tmp_path / "terrain.npy"
        np.save(npy_path, np.linspace(-10, 100, 16, dtype=np.float32))

        return idrisi_dir, npy_path

    def test_full_run_writes_tiles_and_georef(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_terrain_tiles import main
        z, x, y = 12, 2048, 2048
        idrisi_dir, npy_path = self._write_inputs(tmp_path, z, x, y)

        output_dir = tmp_path / "terrain_tiles"

        rc = main([
            "--idrisi", str(idrisi_dir),
            "--npy", str(npy_path),
            "--output", str(output_dir),
            "--min-zoom", str(z),
            "--max-zoom", str(z),
        ])

        assert rc == 0

        georef = json.loads((output_dir / "georef.json").read_text(encoding="utf-8"))
        assert georef["min_zoom"] == z
        assert georef["max_zoom"] == z
        assert georef["crs_epsg"] == 25830

        elevation_tile = output_dir / str(z) / str(x) / f"{y}.png"
        imagery_tile = output_dir / "imagery" / str(z) / str(x) / f"{y}.png"
        assert elevation_tile.exists()
        assert imagery_tile.exists()
