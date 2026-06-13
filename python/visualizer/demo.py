"""
Demo script: runs the full visualizer pipeline with synthetic data.
No MQTT broker needed.

Usage:
    python -m python.visualizer.demo [--renderer 2d|x3d] [--output ./demo_output]

Generates a terrain with a central valley and simulates a flood spreading
outward over several frames.
"""

import argparse
import os
import shutil
from pathlib import Path

import numpy as np

from . import config
from .data_model import SimulationGrid
from .renderers.base import FrameData, GridMeta
from .renderers.registry import create_renderer, create_depth_provider


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

def _make_terrain(rows: int, cols: int) -> np.ndarray:
    """Bowl-shaped terrain: high edges, low centre valley."""
    cy, cx = rows / 2.0, cols / 2.0
    y = np.linspace(0, 1, rows)
    x = np.linspace(0, 1, cols)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    dist = np.sqrt((yy - 0.5) ** 2 + (xx - 0.5) ** 2)
    # Terrain: peaks at edges (~10m), valley at centre (~0m)
    terrain = (dist / dist.max()) * 10.0
    return terrain.astype(np.float32)


def _make_flood_frame(rows: int, cols: int, frame: int, total_frames: int) -> np.ndarray:
    """
    Flood spreads from the centre outward each frame.
    Returns a uint8 palette grid (0=Dry … 5=Extreme Depth).
    """
    cy, cx = rows / 2.0, cols / 2.0
    y = np.arange(rows)
    x = np.arange(cols)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    max_dist = np.sqrt(cy ** 2 + cx ** 2)

    # Flood radius grows each frame
    flood_radius = max_dist * (frame + 1) / total_frames

    grid = np.zeros((rows, cols), dtype=np.uint8)
    # Deeper water closer to centre
    grid[dist <= flood_radius * 0.2] = 5   # Extreme Depth
    grid[dist <= flood_radius * 0.4] = 4   # High Depth
    grid[dist <= flood_radius * 0.6] = 3   # Medium Depth
    grid[dist <= flood_radius * 0.8] = 2   # Low Depth
    grid[dist <= flood_radius] = np.where(
        grid[dist <= flood_radius] == 0, 1, grid[dist <= flood_radius]
    )  # Very Shallow at the flood front
    return grid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(renderer_type: str, output_dir: str,
        rows: int = 60, cols: int = 80,
        cell_size_m: float = 25.0, n_frames: int = 8) -> None:

    output_path = Path(output_dir)
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True)

    print(f"Renderer  : {renderer_type}")
    print(f"Grid      : {rows}x{cols}  cell={cell_size_m}m")
    print(f"Frames    : {n_frames}")
    print(f"Output    : {output_path.resolve()}")
    print()

    # --- build terrain ---
    terrain = _make_terrain(rows, cols)

    # --- wire up the stack ---
    renderer = create_renderer(renderer_type, str(output_path))
    depth_provider = create_depth_provider(config.DEPTH_PROVIDER_TYPE)
    depth_provider.setup(rows, cols)

    meta = GridMeta(
        rows=rows,
        cols=cols,
        cell_size_m=cell_size_m,
        terrain_heights=terrain.flatten(),
    )
    renderer.setup(meta)

    # --- initial frame: all dry ---
    palette_grid = np.zeros((rows, cols), dtype=np.uint8)
    water_depths = depth_provider.get_water_depths(palette_grid)
    renderer.save_snapshot(FrameData(palette_grid=palette_grid, water_depths=water_depths), step_index=0)
    print(f"  step 0 — initial (all dry)")

    # --- flood frames ---
    for frame in range(n_frames):
        palette_grid = _make_flood_frame(rows, cols, frame, n_frames)
        water_depths = depth_provider.get_water_depths(palette_grid)
        renderer.save_snapshot(FrameData(palette_grid=palette_grid, water_depths=water_depths), step_index=frame + 1)
        flooded_cells = int(np.sum(palette_grid > 0))
        print(f"  step {frame + 1} — {flooded_cells} flooded cells")

    renderer.close()

    print()
    if renderer_type == "x3d":
        files = sorted((output_path / "x3d_files").glob("*.html"))
        print(f"X3D files ({len(files)}) in: {output_path / 'x3d_files'}")
        print("  Open any .html file in a browser to view the 3D scene.")
        if files:
            print(f"  First frame: {files[0]}")
    else:
        files = sorted(output_path.glob("*.png"))
        print(f"PNG files ({len(files)}) in: {output_path}")
        if files:
            print(f"  First frame: {files[0]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DanaSim visualizer demo")
    parser.add_argument("--renderer", choices=["2d", "x3d"], default="x3d")
    parser.add_argument("--output", default="demo_output")
    parser.add_argument("--rows", type=int, default=60)
    parser.add_argument("--cols", type=int, default=80)
    parser.add_argument("--cell-size", type=float, default=25.0)
    parser.add_argument("--frames", type=int, default=8)
    args = parser.parse_args()
    run(args.renderer, args.output,
        rows=args.rows, cols=args.cols,
        cell_size_m=args.cell_size, n_frames=args.frames)
