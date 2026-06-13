"""Generate RGBA flood-risk PNG tiles from DanaSim CSV data.

Reads csv_data/ (produced by CSVRenderer) and georef.json (produced by
generate_terrain_tiles.py) and outputs one set of RGBA PNG tiles per
simulation frame. Transparent pixels = dry; colored pixels = flooded.

Run as:
    python -m python.visualizer.tools.generate_flood_tiles \\
        --csv outputs/csv_data/ \\
        --georef tiles/terrain/georef.json \\
        --output tiles/flood/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

from .csv_utils import discover_frames, load_frame, load_meta
from .tile_utils import encode_flood_rgba, tile_bounds_3857, tiles_for_bbox_3857, reproject_tile

_TILE_SIZE = 256


def _load_state_colors(palette_path: Path | None) -> list[tuple[int, int, int]]:
    """Load flood-risk state colors as (R,G,B) 0-255 tuples."""
    defaults = [
        (245, 222, 179),   # 0: Dry
        (153, 204, 255),   # 1: Very Shallow
        (100, 150, 220),   # 2: Low Depth
        (30,  100, 200),   # 3: Medium Depth
        (0,    50, 180),   # 4: High Depth
        (75,    0, 130),   # 5: Extreme Depth
    ]
    if palette_path is None or not palette_path.exists():
        return defaults
    try:
        data = json.loads(palette_path.read_text(encoding="utf-8"))
        flood_risk = data.get("layers", {}).get("flood_risk", [])
        if flood_risk:
            sorted_levels = sorted(flood_risk, key=lambda e: e["value"])
            return [(e["rgba"][0], e["rgba"][1], e["rgba"][2]) for e in sorted_levels]
        x3d = data.get("x3d", {}).get("state_colors", [])
        if x3d:
            return [(int(r*255), int(g*255), int(b*255)) for r, g, b in x3d]
    except Exception:
        pass
    return defaults


def _auto_detect_palette(csv_dir: Path) -> Path | None:
    for parent in csv_dir.parents:
        candidate = parent / "data" / "data_29_10_2024" / "color_palette.json"
        if candidate.exists():
            return candidate
    return None


def _reproject_rgba(rgba: np.ndarray, src_crs: CRS, src_transform,
                    west: float, south: float, east: float, north: float) -> np.ndarray:
    """Reproject (rows, cols, 4) RGBA array into a 256×256 tile."""
    bands = rgba.transpose(2, 0, 1).astype(np.float32)  # (4, H, W)
    result = reproject_tile(
        bands, src_crs, src_transform,
        west, south, east, north,
        resampling=Resampling.nearest,  # nearest for categorical palette data
    )
    # result shape: (4, 256, 256) since input has 4 bands
    # reproject_tile handles multi-band via the (bands, H, W) path
    return result.transpose(1, 2, 0).astype(np.uint8)  # (256, 256, 4)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Generate RGBA flood-risk tiles from DanaSim CSV data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", required=True, help="Path to csv_data/ directory")
    parser.add_argument("--georef", default="tiles/terrain/georef.json",
                        help="Path to georef.json from generate_terrain_tiles")
    parser.add_argument("--output", default="tiles/flood", help="Output tile directory")
    parser.add_argument("--max-zoom", type=int, default=None,
                        help="Override max zoom from georef.json")
    parser.add_argument("--frames", type=int, default=None,
                        help="Limit to first N frames")
    parser.add_argument("--palette", default=None,
                        help="Path to color_palette.json (auto-detected if omitted)")
    args = parser.parse_args(argv)

    csv_dir    = Path(args.csv).resolve()
    georef_path = Path(args.georef).resolve()
    output_dir = Path(args.output).resolve()

    # --- Load metadata ---
    meta   = load_meta(csv_dir)
    rows, cols = meta["rows"], meta["cols"]
    georef = json.loads(georef_path.read_text(encoding="utf-8"))
    min_zoom = georef["min_zoom"]
    max_zoom = georef["max_zoom"]

    dom_west  = georef["dom_west_3857"]
    dom_south = georef["dom_south_3857"]
    dom_east  = georef["dom_east_3857"]
    dom_north = georef["dom_north_3857"]

    src_crs = CRS.from_epsg(georef["crs_epsg"])
    src_transform = from_bounds(
        georef["xll"], georef["yll"], georef["xur"], georef["yur"], cols, rows
    )

    # --- Load colors ---
    palette_path = Path(args.palette) if args.palette else _auto_detect_palette(csv_dir)
    state_colors = _load_state_colors(palette_path)
    log.info("State colors loaded (%d states)", len(state_colors))

    # --- Discover frames ---
    frame_paths = discover_frames(csv_dir)
    if args.frames is not None:
        frame_paths = frame_paths[: args.frames]
    if not frame_paths:
        log.error("No step_XXXXX.csv files found in %s", csv_dir)
        return 1
    log.info("Processing %d frames into %s", len(frame_paths), output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-compute tile list (same for every frame)
    tile_lists: dict[int, list[tuple[int, int]]] = {}
    for z in range(min_zoom, max_zoom + 1):
        tile_lists[z] = list(tiles_for_bbox_3857(z, dom_west, dom_south, dom_east, dom_north))

    manifest_frames = []

    for frame_path in frame_paths:
        step_name = frame_path.stem  # "step_00000"
        log.info("Frame %s ...", step_name)

        palette_grid, _ = load_frame(frame_path, rows, cols)
        rgba_full = encode_flood_rgba(palette_grid, state_colors)

        frame_dir = output_dir / step_name
        total_tiles = 0

        for z in range(min_zoom, max_zoom + 1):
            for x, y in tile_lists[z]:
                w, s, e, n = tile_bounds_3857(z, x, y)
                tile_rgba = _reproject_rgba(rgba_full, src_crs, src_transform, w, s, e, n)

                # Skip fully transparent tiles (no flood in this tile at this zoom)
                if tile_rgba[:, :, 3].max() == 0:
                    continue

                tile_path = frame_dir / str(z) / str(x) / f"{y}.png"
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(tile_rgba, mode="RGBA").save(tile_path, format="PNG")
                total_tiles += 1

        log.info("  %d non-empty tiles written", total_tiles)
        manifest_frames.append({"index": len(manifest_frames), "file": step_name})

    # --- Write manifest.json ---
    manifest = {
        "frames":    manifest_frames,
        "min_zoom":  min_zoom,
        "max_zoom":  max_zoom,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("manifest.json written: %s", manifest_path)
    log.info("Done — %d frames processed", len(manifest_frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
