"""Shared tile math, encoding, and reprojection utilities.

All functions are pure (no filesystem I/O) and fully testable in isolation.
Tile coordinates follow the XYZ/Slippy Map convention used by CesiumJS
WebMercatorTilingScheme: origin at top-left, y increases downward.
"""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject as rio_reproject

# EPSG:3857 half-circumference in metres
_HALF_CIRC = 20037508.3427892
_TILE_SIZE = 256


def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) in EPSG:3857 metres for tile (z, x, y)."""
    n = 2 ** z
    tile_m = _HALF_CIRC * 2 / n
    west  = x * tile_m - _HALF_CIRC
    east  = west + tile_m
    north = _HALF_CIRC - y * tile_m
    south = north - tile_m
    return west, south, east, north


def tiles_for_bbox_3857(
    z: int,
    west: float, south: float, east: float, north: float,
) -> Iterator[tuple[int, int]]:
    """Yield (x, y) tile indices covering the EPSG:3857 bbox at zoom level z."""
    n = 2 ** z
    tile_m = _HALF_CIRC * 2 / n
    eps = 1e-8  # avoid counting a tile whose only overlap is a shared edge
    x_min = max(0, int((west  + _HALF_CIRC) / tile_m))
    x_max = min(n - 1, int((east  + _HALF_CIRC - eps) / tile_m))
    y_min = max(0, int((_HALF_CIRC - north) / tile_m))
    y_max = min(n - 1, int((_HALF_CIRC - south - eps) / tile_m))
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            yield x, y


def encode_terrarium(heights: np.ndarray) -> np.ndarray:
    """Encode a (H, W) float32 height array → (H, W, 3) uint8 RGB using Terrarium scheme.

    Terrarium encoding (used by Mapbox/Maptiler/CesiumJS):
        value = height_m + 32768.0
        R = floor(value / 256)
        G = floor(value) mod 256
        B = floor((value mod 1) * 256)

    Decode in JavaScript: height = (R * 256 + G + B / 256.0) - 32768.0
    Valid height range: -32768m to +32767m (covers all Earth terrain).
    """
    h = heights.astype(np.float64)
    value = np.clip(h + 32768.0, 0.0, 65535.99)
    r = (value / 256).astype(np.uint8)
    g = (value % 256).astype(np.uint8)
    b = ((value % 1) * 256).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def encode_flood_rgba(
    palette_grid: np.ndarray,
    state_colors: list[tuple[int, int, int]],
) -> np.ndarray:
    """Map flood_risk palette (0–5) → (H, W, 4) RGBA uint8.

    State 0 (dry) → fully transparent (alpha=0).
    States 1–5 → opaque colored (alpha=200).

    state_colors: list of (R, G, B) tuples in 0-255 range, one per state.
    """
    rows, cols = palette_grid.shape
    rgba = np.zeros((rows, cols, 4), dtype=np.uint8)
    colors = np.array(state_colors, dtype=np.uint8)
    clipped = np.clip(palette_grid, 0, len(colors) - 1)
    rgba[:, :, :3] = colors[clipped]
    rgba[:, :, 3] = np.where(palette_grid > 0, 200, 0).astype(np.uint8)
    return rgba


def reproject_tile(
    data: np.ndarray,
    src_crs: CRS,
    src_transform,
    west: float, south: float, east: float, north: float,
    resampling: Resampling = Resampling.bilinear,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Reproject a (bands, H, W) or (H, W) array into a 256×256 tile window.

    src_transform: rasterio Affine transform for the source array.
    west/south/east/north: tile bounds in EPSG:3857.
    fill_value: value used for pixels outside the source extent.

    Returns array of same band structure at (bands, 256, 256) or (256, 256).
    No nodata mask is set — avoids rasterio warnings when 0 is a valid data value.
    """
    dst_crs = CRS.from_epsg(3857)
    dst_transform = from_bounds(west, south, east, north, _TILE_SIZE, _TILE_SIZE)

    single_band = data.ndim == 2
    src = data[np.newaxis].astype(np.float32) if single_band else data.astype(np.float32)

    dst = np.full((src.shape[0], _TILE_SIZE, _TILE_SIZE), fill_value=fill_value, dtype=np.float32)

    rio_reproject(
        source=src,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=resampling,
    )

    return dst[0] if single_band else dst
