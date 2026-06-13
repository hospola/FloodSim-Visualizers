"""Tests for X3DSerializer and TiledX3DSerializer."""
from __future__ import annotations

import json

import numpy as np
import pytest

from python.visualizer.renderers.base import FrameData, GridMeta
from python.visualizer.renderers.x3d.colors import X3DColorScheme
from python.visualizer.renderers.x3d.serializer import X3DSerializer
from python.visualizer.renderers.x3d.tiled_serializer import TiledX3DSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta(rows: int = 8, cols: int = 10, cell_size: float = 5.0,
          with_terrain: bool = True) -> GridMeta:
    terrain = None
    if with_terrain:
        terrain = np.linspace(0.0, 50.0, rows * cols, dtype=np.float32)
    return GridMeta(rows=rows, cols=cols, cell_size_m=cell_size, terrain_heights=terrain)


def _frame(rows: int = 8, cols: int = 10) -> FrameData:
    grid = np.zeros((rows, cols), dtype=np.uint8)
    if rows > 2 and cols > 3:
        grid[2, 3] = 3
    if rows > 4 and cols > 5:
        grid[4, 5] = 5
    depths = np.zeros((rows, cols), dtype=np.float32)
    return FrameData(palette_grid=grid, water_depths=depths)


def _colors() -> X3DColorScheme:
    return X3DColorScheme()


# ===========================================================================
# X3DSerializer
# ===========================================================================

class TestX3DSerializerConfigure:
    def test_configure_ok(self) -> None:
        s = X3DSerializer()
        s.configure(_meta())
        assert s._configured is True

    def test_configure_zero_rows_raises(self) -> None:
        s = X3DSerializer()
        with pytest.raises(ValueError):
            s.configure(GridMeta(rows=0, cols=5, cell_size_m=1.0, terrain_heights=None))

    def test_configure_zero_cols_raises(self) -> None:
        s = X3DSerializer()
        with pytest.raises(ValueError):
            s.configure(GridMeta(rows=5, cols=0, cell_size_m=1.0, terrain_heights=None))

    def test_subsample_clipped_to_one(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(), subsample=0)
        assert s._subsample == 1

    def test_subsample_affects_dimensions(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(rows=8, cols=10), subsample=2)
        assert s._rows_s == 4
        assert s._cols_s == 5


class TestX3DSerializerSerialize:
    def test_serialize_returns_html_and_strings(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(), colors=_colors())
        html, (h_str, c_str) = s.serialize(_frame())
        assert "<!DOCTYPE html>" in html
        assert "<ElevationGrid" in html
        assert len(h_str) > 0
        assert len(c_str) > 0

    def test_serialize_without_configure_raises(self) -> None:
        s = X3DSerializer()
        with pytest.raises(RuntimeError):
            s.serialize(_frame())

    def test_serialize_without_terrain(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(with_terrain=False), colors=_colors())
        html, _ = s.serialize(_frame())
        assert "<!DOCTYPE html>" in html

    def test_heights_str_has_correct_count(self) -> None:
        rows, cols = 4, 5
        s = X3DSerializer()
        s.configure(_meta(rows=rows, cols=cols), colors=_colors())
        _, (h_str, _) = s.serialize(_frame(rows=rows, cols=cols))
        n_values = len(h_str.split())
        assert n_values == rows * cols

    def test_colors_str_has_correct_count(self) -> None:
        rows, cols = 4, 5
        s = X3DSerializer()
        s.configure(_meta(rows=rows, cols=cols), colors=_colors())
        _, (_, c_str) = s.serialize(_frame(rows=rows, cols=cols))
        # 3 floats per vertex
        assert len(c_str.split()) == rows * cols * 3


class TestX3DSerializerGeneratePlayer:
    def test_generate_player_returns_html(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(), colors=_colors())
        _, token = s.serialize(_frame())
        player = s.generate_player([token])
        assert "<!DOCTYPE html>" in player
        assert "simFrames" in player

    def test_generate_player_without_configure_raises(self) -> None:
        s = X3DSerializer()
        with pytest.raises(RuntimeError):
            s.generate_player([])

    def test_generate_player_empty_frames(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(), colors=_colors())
        player = s.generate_player([])
        assert "simFrames" in player

    def test_generate_player_multiple_frames(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(), colors=_colors())
        tokens = [s.serialize(_frame())[1] for _ in range(3)]
        player = s.generate_player(tokens)
        assert player.count("{h:") == 3


class TestX3DSerializerHelpers:
    def test_sanitize_nan(self) -> None:
        s = X3DSerializer()
        s.configure(_meta())
        arr = np.array([np.nan, np.inf, -np.inf, 5.0])
        result = s._sanitize(arr)
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    def test_scale_z_flat_terrain_returns_one(self) -> None:
        s = X3DSerializer()
        terrain = np.ones(20, dtype=np.float32) * 10.0
        s.configure(GridMeta(rows=4, cols=5, cell_size_m=5.0, terrain_heights=terrain))
        assert s._scale_z() == pytest.approx(1.0)

    def test_scale_z_none_terrain_returns_one(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(with_terrain=False))
        assert s._scale_z() == pytest.approx(1.0)

    def test_scale_z_normal_terrain(self) -> None:
        s = X3DSerializer()
        terrain = np.linspace(0.0, 100.0, 20, dtype=np.float32)
        s.configure(GridMeta(rows=4, cols=5, cell_size_m=5.0, terrain_heights=terrain))
        scale = s._scale_z()
        assert scale > 0.0

    def test_compute_viewpoint_returns_strings(self) -> None:
        s = X3DSerializer()
        s.configure(_meta())
        pos, orient = s._compute_viewpoint(10.0, 8.0, 2.0)
        assert len(pos.split()) == 3
        assert len(orient.split()) == 4

    def test_get_colors_str_all_dry(self) -> None:
        s = X3DSerializer()
        s.configure(_meta(rows=2, cols=2), colors=_colors())
        frame = FrameData(
            palette_grid=np.zeros((2, 2), dtype=np.uint8),
            water_depths=np.zeros((2, 2), dtype=np.float32),
        )
        c_str = s._get_colors_str(frame)
        # 4 vertices × 3 channels = 12 values, all matching state 0 color
        vals = [float(v) for v in c_str.split()]
        assert len(vals) == 12


# ===========================================================================
# TiledX3DSerializer
# ===========================================================================

class TestTiledX3DSerializerConfigure:
    def test_configure_ok(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=16, cols=20), chunk_size=8)
        assert s._configured is True

    def test_configure_zero_rows_raises(self) -> None:
        s = TiledX3DSerializer()
        with pytest.raises(ValueError):
            s.configure(GridMeta(rows=0, cols=5, cell_size_m=1.0, terrain_heights=None))

    def test_chunk_count(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=16, cols=20), chunk_size=8)
        assert s._n_chunks_r == 2
        assert s._n_chunks_c == 3  # ceil(20/8) = 3

    def test_wet_mask_none_treats_all_as_wet(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4, wet_mask=None)
        assert s._wet_tiles is None

    def test_wet_mask_filters_dry_tiles(self) -> None:
        rows, cols = 8, 8
        wet_mask = np.zeros(rows * cols, dtype=bool)
        wet_mask[0] = True  # only first cell is wet → only tile (0,0) is wet
        s = TiledX3DSerializer()
        s.configure(_meta(rows=rows, cols=cols), chunk_size=4, wet_mask=wet_mask)
        assert (0, 0) in s._wet_tiles
        assert len(s._wet_tiles) == 1

    def test_custom_lod_subsamples(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(), chunk_size=4, lod_subsamples=[1, 2])
        assert s._lod_subsamples == [1, 2]


class TestTiledX3DSerializerSerialize:
    def test_serialize_returns_html_and_token(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4)
        html, token = s.serialize(_frame(rows=8, cols=8))
        assert "<!DOCTYPE html>" in html
        assert "<LOD" in html
        token_dict = json.loads(token)
        assert len(token_dict) > 0

    def test_serialize_without_configure_raises(self) -> None:
        s = TiledX3DSerializer()
        with pytest.raises(RuntimeError):
            s.serialize(_frame())

    def test_token_keys_format(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4, lod_subsamples=[1, 4])
        _, token = s.serialize(_frame(rows=8, cols=8))
        token_dict = json.loads(token)
        for key in token_dict:
            parts = key.split("_")
            assert len(parts) == 3

    def test_serialize_empty_frame(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4)
        html, token = s.serialize_empty_frame()
        assert "<!DOCTYPE html>" in html
        token_dict = json.loads(token)
        assert len(token_dict) > 0

    def test_serialize_without_terrain(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8, with_terrain=False), chunk_size=4)
        html, _ = s.serialize(_frame(rows=8, cols=8))
        assert "<ElevationGrid" in html


class TestTiledX3DSerializerGeneratePlayer:
    def test_generate_player_returns_html(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4)
        _, token = s.serialize(_frame(rows=8, cols=8))
        player = s.generate_player([token])
        assert "<!DOCTYPE html>" in player
        assert "simFrames" in player

    def test_generate_player_without_configure_raises(self) -> None:
        s = TiledX3DSerializer()
        with pytest.raises(RuntimeError):
            s.generate_player([])

    def test_generate_player_frame_count_in_html(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8), chunk_size=4)
        tokens = [s.serialize(_frame(rows=8, cols=8))[1] for _ in range(2)]
        player = s.generate_player(tokens)
        assert "frames=2" in player


class TestTiledX3DSerializerHelpers:
    def test_sanitize(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta())
        arr = np.array([np.nan, np.inf, -np.inf])
        result = s._sanitize(arr)
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    def test_scale_z_flat_terrain(self) -> None:
        terrain = np.ones(80, dtype=np.float32) * 5.0
        s = TiledX3DSerializer()
        s.configure(GridMeta(rows=8, cols=10, cell_size_m=5.0, terrain_heights=terrain))
        assert s._scale_z() == pytest.approx(1.0)

    def test_scale_z_none_terrain(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(with_terrain=False))
        assert s._scale_z() == pytest.approx(1.0)

    def test_extract_terrain_chunk_shape(self) -> None:
        rows, cols, cs = 8, 8, 4
        s = TiledX3DSerializer()
        s.configure(_meta(rows=rows, cols=cols), chunk_size=cs)
        chunk = s._extract_terrain_chunk(0, 0, 1)
        assert chunk.shape == (cs * cs,)

    def test_extract_terrain_chunk_no_terrain(self) -> None:
        s = TiledX3DSerializer()
        s.configure(_meta(rows=8, cols=8, with_terrain=False), chunk_size=4)
        chunk = s._extract_terrain_chunk(0, 0, 1)
        assert (chunk == 0.0).all()
