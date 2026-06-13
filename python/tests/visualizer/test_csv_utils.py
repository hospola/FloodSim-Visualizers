"""Tests for tools/csv_utils.py — pure file-loading utilities."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import numpy as np
import pytest

from python.visualizer.tools.csv_utils import (
    build_wet_mask,
    discover_frames,
    load_frame,
    load_meta,
    load_terrain,
)


@pytest.fixture()
def csv_dir(tmp_path: Path) -> Path:
    rows, cols, cell_size = 4, 5, 10.0

    (tmp_path / "meta.json").write_text(
        json.dumps({"rows": rows, "cols": cols, "cell_size_m": cell_size}),
        encoding="utf-8",
    )

    terrain = np.arange(rows * cols, dtype=np.float32)
    np.save(tmp_path / "terrain.npy", terrain)

    # step_00000: cell (1,2)=3, cell (0,0)=1
    (tmp_path / "step_00000.csv").write_text(
        textwrap.dedent("""\
            # rows=4 cols=5 cell_size_m=10.0
            row,col,flood_risk
            0,0,1
            1,2,3
        """),
        encoding="utf-8",
    )

    # step_00001: cell (3,4)=5
    (tmp_path / "step_00001.csv").write_text(
        textwrap.dedent("""\
            # rows=4 cols=5 cell_size_m=10.0
            row,col,flood_risk
            3,4,5
        """),
        encoding="utf-8",
    )

    return tmp_path


def test_load_meta(csv_dir: Path) -> None:
    meta = load_meta(csv_dir)
    assert meta["rows"] == 4
    assert meta["cols"] == 5
    assert meta["cell_size_m"] == 10.0


def test_load_terrain(csv_dir: Path) -> None:
    terrain = load_terrain(csv_dir)
    assert terrain.dtype == np.float32
    assert terrain.shape == (20,)
    assert terrain[0] == pytest.approx(0.0)
    assert terrain[19] == pytest.approx(19.0)


def test_load_frame_values(csv_dir: Path) -> None:
    grid, depths = load_frame(csv_dir / "step_00000.csv", rows=4, cols=5)
    assert grid.dtype == np.uint8
    assert grid.shape == (4, 5)
    assert grid[0, 0] == 1
    assert grid[1, 2] == 3
    assert grid[0, 1] == 0  # dry cell not in CSV


def test_load_frame_returns_none_depths(csv_dir: Path) -> None:
    _, depths = load_frame(csv_dir / "step_00000.csv", rows=4, cols=5)
    assert depths is None


def test_load_frame_ignores_out_of_bounds(tmp_path: Path) -> None:
    (tmp_path / "bad.csv").write_text(
        "# rows=2 cols=2 cell_size_m=1.0\nrow,col,flood_risk\n99,99,5\n0,0,2\n",
        encoding="utf-8",
    )
    grid, _ = load_frame(tmp_path / "bad.csv", rows=2, cols=2)
    assert grid[0, 0] == 2
    assert grid.max() == 2


def test_discover_frames_sorted(csv_dir: Path) -> None:
    frames = discover_frames(csv_dir)
    assert len(frames) == 2
    assert frames[0].name == "step_00000.csv"
    assert frames[1].name == "step_00001.csv"


def test_discover_frames_empty(tmp_path: Path) -> None:
    assert discover_frames(tmp_path) == []


def test_build_wet_mask(csv_dir: Path) -> None:
    frames = discover_frames(csv_dir)
    mask = build_wet_mask(frames, rows=4, cols=5)
    assert mask.shape == (20,)
    assert mask.dtype == bool
    # cell (0,0) → flat index 0
    assert mask[0] is np.bool_(True)
    # cell (1,2) → flat index 1*5+2=7
    assert mask[7] is np.bool_(True)
    # cell (3,4) → flat index 3*5+4=19
    assert mask[19] is np.bool_(True)
    # dry cell (0,1) → flat index 1
    assert mask[1] is np.bool_(False)


def test_build_wet_mask_empty(tmp_path: Path) -> None:
    mask = build_wet_mask([], rows=3, cols=3)
    assert not mask.any()
