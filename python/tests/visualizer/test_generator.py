"""Tests for tools/x3d_player/generator.py and tools/generate_x3d.py."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import numpy as np
import pytest

from python.visualizer.tools.x3d_player.generator import (
    _auto_detect_palette,
    _encode_flood_png,
    _encode_terrain_png,
    _load_state_colors,
    _state_color_strings,
    _viewpoints,
    copy_js_assets,
    generate_player,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def csv_dir(tmp_path: Path) -> Path:
    """Minimal csv_data/ directory with meta, terrain and one frame."""
    rows, cols = 4, 6
    (tmp_path / "meta.json").write_text(
        json.dumps({"rows": rows, "cols": cols, "cell_size_m": 5.0}),
        encoding="utf-8",
    )
    terrain = np.linspace(0.0, 50.0, rows * cols, dtype=np.float32)
    np.save(tmp_path / "terrain.npy", terrain)

    (tmp_path / "step_00000.csv").write_text(
        textwrap.dedent("""\
            # rows=4 cols=6 cell_size_m=5.0
            row,col,flood_risk
            1,2,3
            2,4,5
        """),
        encoding="utf-8",
    )
    return tmp_path


# ===========================================================================
# PNG encoders
# ===========================================================================

class TestEncoders:
    def test_encode_terrain_png_returns_bytes(self) -> None:
        terrain = np.linspace(0.0, 100.0, 12).reshape(3, 4).astype(np.float32)
        data, min_h, max_h = _encode_terrain_png(terrain)
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert min_h == pytest.approx(0.0, abs=0.1)
        assert max_h == pytest.approx(100.0, abs=0.1)

    def test_encode_terrain_png_nodata_excluded(self) -> None:
        terrain = np.array([[-9999.0, 10.0], [20.0, 30.0]], dtype=np.float32)
        _, min_h, max_h = _encode_terrain_png(terrain)
        assert min_h >= 10.0  # nodata cell excluded from range

    def test_encode_terrain_png_constant(self) -> None:
        terrain = np.ones((3, 3), dtype=np.float32) * 5.0
        data, min_h, max_h = _encode_terrain_png(terrain)
        assert max_h > min_h  # avoids division-by-zero via +1.0
        assert len(data) > 0

    def test_encode_terrain_png_empty_valid(self) -> None:
        terrain = np.full((2, 2), -9999.0, dtype=np.float32)
        data, min_h, max_h = _encode_terrain_png(terrain)
        assert min_h == pytest.approx(0.0)
        assert max_h == pytest.approx(100.0)

    def test_encode_flood_png_returns_bytes(self) -> None:
        palette = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint8)
        data = _encode_flood_png(palette)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_encode_flood_png_shape_preserved(self) -> None:
        from PIL import Image
        from io import BytesIO
        palette = np.zeros((4, 6), dtype=np.uint8)
        palette[1, 2] = 3
        data = _encode_flood_png(palette)
        img = Image.open(BytesIO(data))
        assert img.size == (6, 4)  # PIL uses (width, height)


# ===========================================================================
# Palette loading
# ===========================================================================

class TestLoadStateColors:
    def test_returns_defaults_when_none(self) -> None:
        colors = _load_state_colors(None)
        assert len(colors) == 6
        assert all(len(c) == 3 for c in colors)

    def test_returns_defaults_when_missing(self, tmp_path: Path) -> None:
        colors = _load_state_colors(tmp_path / "nonexistent.json")
        assert len(colors) == 6

    def test_loads_flood_risk_section(self, tmp_path: Path) -> None:
        palette = {
            "layers": {
                "flood_risk": [
                    {"value": i, "rgba": [i * 10, i * 20, i * 30, 255]}
                    for i in range(6)
                ]
            }
        }
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        colors = _load_state_colors(p)
        assert len(colors) == 6
        assert colors[1] == (10, 20, 30)

    def test_loads_x3d_section_fallback(self, tmp_path: Path) -> None:
        palette = {
            "x3d": {
                "state_colors": [[r / 255, g / 255, b / 255]
                                  for r, g, b in [(10, 20, 30)] * 6]
            }
        }
        p = tmp_path / "palette.json"
        p.write_text(json.dumps(palette), encoding="utf-8")
        colors = _load_state_colors(p)
        assert len(colors) == 6

    def test_returns_defaults_on_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        colors = _load_state_colors(p)
        assert len(colors) == 6


# ===========================================================================
# Template helpers
# ===========================================================================

class TestTemplateHelpers:
    def test_state_color_strings_format(self) -> None:
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
                  (128, 128, 128), (10, 20, 30), (50, 100, 150)]
        strings = _state_color_strings(colors)
        assert len(strings) == 6
        assert strings[0] == "1.00 0.00 0.00"

    def test_viewpoints_keys(self) -> None:
        vp = _viewpoints(1000.0, 800.0, 50.0)
        assert "overview" in vp
        assert "cenital" in vp
        assert "lateral" in vp
        for v in vp.values():
            assert "pos" in v
            assert "orient" in v

    def test_auto_detect_palette_not_found(self, tmp_path: Path) -> None:
        result = _auto_detect_palette(tmp_path)
        assert result is None


# ===========================================================================
# generate_player
# ===========================================================================

class TestGeneratePlayer:
    def _state_colors(self):
        return [(i * 40, i * 20, i * 10) for i in range(6)]

    def _terrain_b64(self) -> str:
        import base64
        terrain = np.zeros((4, 6), dtype=np.float32)
        data, _, _ = _encode_terrain_png(terrain)
        return base64.b64encode(data).decode("ascii")

    def test_returns_html(self) -> None:
        html = generate_player(
            png_cols=6, png_rows=4, png_res_m=5.0,
            orig_cols=6, orig_rows=4, cell_size_m=5.0,
            min_h=0.0, max_h=50.0,
            terrain_b64=self._terrain_b64(),
            frame_names=["step_00000"],
            state_colors=self._state_colors(),
        )
        assert "<!DOCTYPE html>" in html
        assert "step_00000" in html
        assert "__CONFIG__" in html

    def test_multiple_frames(self) -> None:
        html = generate_player(
            png_cols=6, png_rows=4, png_res_m=5.0,
            orig_cols=6, orig_rows=4, cell_size_m=5.0,
            min_h=0.0, max_h=50.0,
            terrain_b64=self._terrain_b64(),
            frame_names=["step_00000", "step_00001", "step_00002"],
            state_colors=self._state_colors(),
        )
        assert "step_00001" in html
        assert "step_00002" in html

    def test_empty_frames(self) -> None:
        html = generate_player(
            png_cols=6, png_rows=4, png_res_m=5.0,
            orig_cols=6, orig_rows=4, cell_size_m=5.0,
            min_h=0.0, max_h=50.0,
            terrain_b64=self._terrain_b64(),
            frame_names=[],
            state_colors=self._state_colors(),
        )
        assert "<!DOCTYPE html>" in html


# ===========================================================================
# copy_js_assets
# ===========================================================================

class TestCopyJsAssets:
    def test_copies_js_directory(self, tmp_path: Path) -> None:
        copy_js_assets(tmp_path)
        assert (tmp_path / "js").is_dir()
        assert (tmp_path / "js" / "app.js").exists()

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        js_dir = tmp_path / "js"
        js_dir.mkdir()
        (js_dir / "stale.js").write_text("stale", encoding="utf-8")
        copy_js_assets(tmp_path)
        assert not (js_dir / "stale.js").exists()


# ===========================================================================
# generator.main CLI
# ===========================================================================

class TestGeneratorMain:
    def test_main_generates_player(self, csv_dir: Path, tmp_path: Path) -> None:
        from python.visualizer.tools.x3d_player.generator import main
        out = tmp_path / "out"
        rc = main(["--csv", str(csv_dir), "--output", str(out)])
        assert rc == 0
        assert (out / "player.html").exists()
        assert (out / "flood" / "step_00000.png").exists()
        assert (out / "js" / "app.js").exists()

    def test_main_missing_csv_dir_returns_error(self, tmp_path: Path) -> None:
        from python.visualizer.tools.x3d_player.generator import main
        rc = main(["--csv", str(tmp_path / "nonexistent"), "--output", str(tmp_path / "out")])
        assert rc != 0

    def test_main_with_frame_limit(self, csv_dir: Path, tmp_path: Path) -> None:
        from python.visualizer.tools.x3d_player.generator import main
        out = tmp_path / "out"
        rc = main(["--csv", str(csv_dir), "--output", str(out), "--frames", "1"])
        assert rc == 0
        assert (out / "player.html").exists()


# ===========================================================================
# generate_x3d.main CLI
# ===========================================================================

class TestGenerateX3dMain:
    def test_flat_mode(self, csv_dir: Path, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        out = tmp_path / "out"
        rc = main([str(csv_dir), "--output", str(out), "--subsample", "1"])
        assert rc == 0
        assert (out / "player.html").exists()
        assert (out / "step_00000.html").exists()

    def test_flat_mode_player_only(self, csv_dir: Path, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        out = tmp_path / "out"
        rc = main([str(csv_dir), "--output", str(out), "--player-only"])
        assert rc == 0
        assert (out / "player.html").exists()
        assert not (out / "step_00000.html").exists()

    def test_lod_mode(self, csv_dir: Path, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        out = tmp_path / "out"
        rc = main([str(csv_dir), "--output", str(out), "--lod",
                   "--lod-chunk", "2", "--frames", "1"])
        assert rc == 0
        assert (out / "player.html").exists()

    def test_missing_data_dir_returns_error(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        rc = main([str(tmp_path / "nonexistent")])
        assert rc == 1

    def test_no_frames_returns_error(self, tmp_path: Path) -> None:
        from python.visualizer.tools.generate_x3d import main
        rows, cols = 4, 6
        (tmp_path / "meta.json").write_text(
            json.dumps({"rows": rows, "cols": cols, "cell_size_m": 5.0}),
            encoding="utf-8",
        )
        np.save(tmp_path / "terrain.npy", np.zeros(rows * cols, dtype=np.float32))
        rc = main([str(tmp_path)])
        assert rc == 1
