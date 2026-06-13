"""Offline X3D generator for DanaSim CSV data.

Reads a csv_data/ directory produced by CSVRenderer and generates X3D HTML files.
Supports flat (single-mesh) output and tiled LOD output.

Usage:
    python -m python.visualizer.tools.generate_x3d <data_dir> [options]

    # Flat output, subsample 8x (better than 32x, still fast):
    python -m python.visualizer.tools.generate_x3d sim_outputs/csv_data/ --subsample 8

    # Tiled LOD output (full resolution, browser-friendly):
    python -m python.visualizer.tools.generate_x3d sim_outputs/csv_data/ --lod
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

from .csv_utils import load_meta, load_terrain, load_frame, discover_frames, build_wet_mask


def _auto_detect_palette(data_dir: Path) -> Path | None:
    """Try to find color_palette.json relative to the project root."""
    for parent in data_dir.parents:
        candidate = parent / "data" / "data_29_10_2024" / "color_palette.json"
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Offline X3D generator — reads csv_data/ and writes X3D HTML files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("data_dir", help="Path to csv_data/ directory")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory (default: <data_dir>/../x3d_output)")
    parser.add_argument("-s", "--subsample", type=int, default=1,
                        help="Subsample factor for flat (non-LOD) output")
    parser.add_argument("--lod", action="store_true",
                        help="Enable tiled LOD mode")
    parser.add_argument("--lod-chunk", type=int, default=256,
                        help="Chunk size in original cells (LOD mode)")
    parser.add_argument("--lod-subsamples", default="1,4,16",
                        help="Comma-separated subsample levels per LOD (LOD mode)")
    parser.add_argument("--lod-ranges", default="5000,20000",
                        help="Comma-separated camera distances for LOD transitions (LOD mode)")
    parser.add_argument("--frames", type=int, default=None,
                        help="Limit to first N frames (useful for testing)")
    parser.add_argument("--palette", default=None,
                        help="Path to color_palette.json")
    parser.add_argument("--player-only", action="store_true",
                        help="Only write player.html, skip per-frame HTML files")

    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        log.error("data_dir not found: %s", data_dir)
        return 1

    output_dir = Path(args.output).resolve() if args.output else (data_dir.parent / "x3d_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load static data
    meta = load_meta(data_dir)
    rows, cols = meta["rows"], meta["cols"]
    terrain = load_terrain(data_dir)
    log.info("Grid: %dx%d  cell_size: %.2fm", rows, cols, meta["cell_size_m"])

    # Deferred project imports
    from ..renderers.base import FrameData, GridMeta
    from ..renderers.x3d.colors import load_colors

    palette_path = Path(args.palette) if args.palette else _auto_detect_palette(data_dir)
    colors = load_colors(palette_path)

    grid_meta = GridMeta(
        rows=rows,
        cols=cols,
        cell_size_m=meta["cell_size_m"],
        terrain_heights=terrain,
    )

    # Build serializer
    lod_subsamples = [int(x) for x in args.lod_subsamples.split(",")]
    lod_ranges = [float(x) for x in args.lod_ranges.split(",")]

    if args.lod:
        from ..renderers.x3d.tiled_serializer import TiledX3DSerializer

        # Pre-pass: find all cells ever wet across all frames so dry tiles get
        # only the coarsest LOD level, dramatically reducing file size.
        all_frame_paths = discover_frames(data_dir)
        if args.frames is not None:
            all_frame_paths = all_frame_paths[: args.frames]
        log.info("Pre-pass: scanning %d frames for wet cells...", len(all_frame_paths))
        wet_mask = build_wet_mask(all_frame_paths, rows, cols)
        log.info("Wet cells: %d / %d (%.1f%%)",
                 int(wet_mask.sum()), rows * cols, 100 * wet_mask.mean())

        serializer = TiledX3DSerializer()
        serializer.configure(
            grid_meta,
            colors=colors,
            chunk_size=args.lod_chunk,
            lod_subsamples=lod_subsamples,
            lod_ranges=lod_ranges,
            wet_mask=wet_mask,
        )
        log.info("LOD mode: chunk=%d  subsamples=%s  ranges=%s",
                 args.lod_chunk, lod_subsamples, lod_ranges)
    else:
        from ..renderers.x3d.serializer import X3DSerializer
        serializer = X3DSerializer()
        serializer.configure(grid_meta, colors=colors, subsample=args.subsample)
        log.info("Flat mode: subsample=%d", args.subsample)

    # Process frames
    frame_paths = discover_frames(data_dir)
    if args.frames is not None:
        frame_paths = frame_paths[: args.frames]

    if not frame_paths:
        log.warning("No step_XXXXX.csv files found in %s", data_dir)
        return 1

    log.info("Processing %d frames...", len(frame_paths))
    frame_tokens: list = []

    for i, csv_path in enumerate(frame_paths):
        palette_grid, water_depths = load_frame(csv_path, rows, cols)
        if water_depths is None:
            water_depths = np.zeros((rows, cols), dtype=np.float32)
        frame = FrameData(palette_grid=palette_grid, water_depths=water_depths)
        html, token = serializer.serialize(frame)
        frame_tokens.append(token)

        if not args.player_only:
            out_path = output_dir / (csv_path.stem + ".html")
            out_path.write_text(html, encoding="utf-8")

        log.info("Frame %d/%d — %s", i + 1, len(frame_paths), csv_path.name)

    player_html = serializer.generate_player(frame_tokens)
    player_path = output_dir / "player.html"
    player_path.write_text(player_html, encoding="utf-8")
    log.info("Done. Player: %s", player_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
