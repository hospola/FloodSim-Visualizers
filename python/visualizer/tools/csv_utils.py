"""Shared CSV data-loading utilities for DanaSim offline tools.

All functions are pure (no side effects beyond reading files) and have no
dependency on the visualizer's MQTT or rendering code.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


def load_meta(data_dir: Path) -> dict:
    """Return dict with rows, cols, cell_size_m."""
    return json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))


def load_terrain(data_dir: Path) -> np.ndarray:
    """Return float32 flat terrain array."""
    return np.load(data_dir / "terrain.npy").astype(np.float32)


def load_frame(csv_path: Path, rows: int, cols: int) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct palette_grid (uint8) from a sparse CSV.

    Returns (palette_grid, None) — water_depths are no longer stored in CSV
    and must be derived from palette_grid via PaletteDepthProvider if needed.
    Shape (rows, cols). Dry cells are 0.
    """
    palette_grid = np.zeros((rows, cols), dtype=np.uint8)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header_skipped = False
        for row_vals in reader:
            if not row_vals or row_vals[0].startswith("#"):
                continue
            if not header_skipped:
                header_skipped = True
                continue
            r, c = int(row_vals[0]), int(row_vals[1])
            if 0 <= r < rows and 0 <= c < cols:
                palette_grid[r, c] = int(row_vals[2])
    return palette_grid, None


def discover_frames(data_dir: Path) -> list[Path]:
    """Return sorted list of step_XXXXX.csv paths."""
    return sorted(data_dir.glob("step_?????.csv"))


def build_wet_mask(frame_paths: list[Path], rows: int, cols: int) -> np.ndarray:
    """Return flat boolean array (rows*cols) — True where any cell is ever wet."""
    wet = np.zeros(rows * cols, dtype=bool)
    for csv_path in frame_paths:
        palette_grid, _ = load_frame(csv_path, rows, cols)
        wet |= (palette_grid.flatten() > 0)
    return wet
