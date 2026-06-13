"""Generate Terrarium-encoded terrain PNG tiles from IDRISI topo_bathy data.

Reads the .doc file for spatial reference and the .img file (or a terrain.npy
override) for height values. Outputs a tile pyramid in EPSG:3857 XYZ format
plus a georef.json used by generate_flood_tiles.py.

Run as:
    python -m python.visualizer.tools.generate_terrain_tiles \\
        --idrisi data/data_29_10_2024/topo_bathy/ \\
        --npy outputs/csv_data/terrain.npy \\
        --output tiles/terrain/

The --npy flag is strongly recommended: loading terrain.npy is seconds vs
minutes for the raw ASCII .img file.
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

from .tile_utils import encode_terrarium, tile_bounds_3857, tiles_for_bbox_3857, reproject_tile

_NODATA = -9999.0
_TILE_SIZE = 256

# Elevation → RGB colormap for terrain imagery tiles.
# Breakpoints: (max_height_m, R, G, B)
_ELEVATION_COLORMAP = [
    (-10,  20,  60, 150),   # deep sea
    (  0,  50, 100, 180),   # shallow sea / bathymetry
    (  5, 210, 195, 145),   # coastal sand
    ( 30, 185, 205, 130),   # lowland green
    (100, 140, 170,  90),   # rolling terrain
    (300, 130, 110,  75),   # hills
    (9999, 200, 190, 180),  # high mountains
]


def _hillshade(heights: np.ndarray, azimuth_deg: float = 315.0,
               altitude_deg: float = 45.0, z_factor: float = 4.0) -> np.ndarray:
    """Compute hillshade intensity (H, W) float32 in [0, 1].

    azimuth_deg: sun direction (315 = northwest, standard cartographic convention)
    altitude_deg: sun elevation above horizon
    z_factor: vertical exaggeration for shading — increase for flatter terrain
    """
    az  = np.radians(360.0 - azimuth_deg + 90.0)  # convert to math angles
    alt = np.radians(altitude_deg)

    # np.gradient returns (d/d_row, d/d_col); rows increase southward so negate dy
    dy, dx = np.gradient(heights.astype(np.float64))
    dy = -dy  # correct for row-down coordinate system

    slope  = np.arctan(z_factor * np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(dy, dx)  # angle of steepest ascent in math coords

    shade = (np.cos(alt) * np.cos(slope)
             + np.sin(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(shade, 0.0, 1.0).astype(np.float32)


def encode_colormap(heights: np.ndarray) -> np.ndarray:
    """Map (H, W) float32 heights → (H, W, 3) uint8 RGB: elevation colormap + hillshade."""
    h, w = heights.shape

    # Base elevation color
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    prev_max = -np.inf
    for max_h, r, g, b in _ELEVATION_COLORMAP:
        mask = (heights > prev_max) & (heights <= max_h)
        rgb[mask] = (r, g, b)
        prev_max = max_h

    # Hillshade: ambient light + directional shading
    shade = _hillshade(heights)
    ambient, diffuse = 0.35, 0.65
    lit = ambient + diffuse * shade[:, :, np.newaxis]
    return np.clip(rgb * lit, 0, 255).astype(np.uint8)


def _read_doc(idrisi_dir: Path, stem: str = "topo_bathy") -> dict:
    """Parse key fields from a .doc metadata file."""
    doc_path = idrisi_dir / f"{stem}.doc"
    meta = {}
    with doc_path.open(encoding="utf-8") as fh:
        for line in fh:
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return {
        "cols":      int(meta["columns"]),
        "rows":      int(meta["rows"]),
        "min_x":     float(meta["min. X"]),
        "max_x":     float(meta["max. X"]),
        "min_y":     float(meta["min. Y"]),
        "max_y":     float(meta["max. Y"]),
        "cell_size": float(meta.get("resolution", meta.get("cell size", "5.0"))),
        "crs_str":   meta.get("ref. system", "EPSG:25830"),
    }


def _load_heights(idrisi_dir: Path, stem: str, npy_path: Path | None,
                  rows: int, cols: int) -> np.ndarray:
    """Return (rows, cols) float32 heights with nodata replaced by 0."""
    log = logging.getLogger(__name__)
    if npy_path is not None:
        log.info("Loading heights from %s", npy_path)
        heights = np.load(npy_path).astype(np.float32).reshape(rows, cols)
    else:
        img_path = idrisi_dir / f"{stem}.img"
        log.info("Loading heights from %s (this may take several minutes)", img_path)
        heights = np.loadtxt(img_path, dtype=np.float32).reshape(rows, cols)

    nodata_count = int((heights <= _NODATA).sum())
    if nodata_count:
        log.debug("Replacing %d nodata cells with 0", nodata_count)
        heights = np.where(heights <= _NODATA, 0.0, heights)
    log.info("Heights loaded: min=%.2f max=%.2f", float(heights.min()), float(heights.max()))
    return heights


def _bbox_3857(doc: dict) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) in EPSG:3857 for the IDRISI domain."""
    from pyproj import Transformer
    src_crs = doc["crs_str"]
    transformer = Transformer.from_crs(src_crs, "EPSG:3857", always_xy=True)
    west, south = transformer.transform(doc["min_x"], doc["min_y"])
    east, north = transformer.transform(doc["max_x"], doc["max_y"])
    return west, south, east, north


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Generate Terrarium terrain tiles from IDRISI topo_bathy data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--idrisi", required=True,
                        help="Directory containing topo_bathy.doc (and optionally .img)")
    parser.add_argument("--npy", default=None,
                        help="Path to terrain.npy — faster alternative to reading .img")
    parser.add_argument("--stem", default="topo_bathy",
                        help="Base filename stem (without extension)")
    parser.add_argument("--output", default="tiles/terrain",
                        help="Output tile directory")
    parser.add_argument("--min-zoom", type=int, default=8)
    parser.add_argument("--max-zoom", type=int, default=13)
    args = parser.parse_args(argv)

    idrisi_dir = Path(args.idrisi).resolve()
    output_dir = Path(args.output).resolve()
    npy_path   = Path(args.npy).resolve() if args.npy else None

    # --- Read spatial metadata ---
    log.info("Reading metadata from %s/%s.doc", idrisi_dir, args.stem)
    doc = _read_doc(idrisi_dir, args.stem)
    rows, cols = doc["rows"], doc["cols"]
    log.info("Grid: %dx%d  cell_size: %.2fm  CRS: %s", rows, cols, doc["cell_size"], doc["crs_str"])

    # --- Load heights ---
    heights = _load_heights(idrisi_dir, args.stem, npy_path, rows, cols)

    # --- Build source rasterio transform (EPSG:25830) ---
    src_crs = CRS.from_user_input(doc["crs_str"])
    src_transform = from_bounds(doc["min_x"], doc["min_y"], doc["max_x"], doc["max_y"], cols, rows)

    # --- Compute domain in EPSG:3857 ---
    dom_west, dom_south, dom_east, dom_north = _bbox_3857(doc)
    log.info("Domain EPSG:3857: W=%.0f S=%.0f E=%.0f N=%.0f",
             dom_west, dom_south, dom_east, dom_north)

    # --- Generate tiles (elevation + colormap imagery) ---
    output_dir.mkdir(parents=True, exist_ok=True)
    imagery_dir = output_dir / "imagery"
    imagery_dir.mkdir(parents=True, exist_ok=True)
    total_tiles = 0

    for z in range(args.min_zoom, args.max_zoom + 1):
        tile_list = list(tiles_for_bbox_3857(z, dom_west, dom_south, dom_east, dom_north))
        log.info("Zoom %d: %d tiles", z, len(tile_list))

        for x, y in tile_list:
            w, s, e, n = tile_bounds_3857(z, x, y)

            tile_heights = reproject_tile(
                heights, src_crs, src_transform,
                w, s, e, n,
                resampling=Resampling.bilinear,
            )

            # Terrarium-encoded elevation tile (for 3D terrain height)
            tile_path = output_dir / str(z) / str(x) / f"{y}.png"
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(encode_terrarium(tile_heights), mode="RGB").save(tile_path, format="PNG")

            # Colormap imagery tile (for base layer visual)
            img_path = imagery_dir / str(z) / str(x) / f"{y}.png"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(encode_colormap(tile_heights), mode="RGB").save(img_path, format="PNG")

            total_tiles += 1

        log.info("Zoom %d done", z)

    # --- Write georef.json ---
    georef = {
        "xll":        doc["min_x"],
        "yll":        doc["min_y"],
        "xur":        doc["max_x"],
        "yur":        doc["max_y"],
        "rows":       rows,
        "cols":       cols,
        "cell_size_m": doc["cell_size"],
        "crs_epsg":   25830,
        "min_zoom":   args.min_zoom,
        "max_zoom":   args.max_zoom,
        "dom_west_3857":  dom_west,
        "dom_south_3857": dom_south,
        "dom_east_3857":  dom_east,
        "dom_north_3857": dom_north,
    }
    georef_path = output_dir / "georef.json"
    georef_path.write_text(json.dumps(georef, indent=2), encoding="utf-8")

    log.info("Done — %d tiles written to %s", total_tiles, output_dir)
    log.info("georef.json: %s", georef_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
