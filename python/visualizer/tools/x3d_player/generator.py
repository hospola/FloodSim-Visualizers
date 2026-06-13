"""X3D heightmap player generator.

Reads simulation CSV output and produces:

  - ``player.html``        — main page, references ``js/app.js`` as a module
  - ``js/`` tree            — ES modules copied verbatim from ``static/js/``
  - ``flood/*.png``         — one PNG per simulation frame

The HTML embeds the terrain heightmap as a base64 data URL and CSS inline,
so only ``player.html`` plus the ``js/`` and ``flood/`` directories are needed
to serve the viewer.

Run as::

    python -m python.visualizer.tools.x3d_player \\
        --csv outputs/csv_data/ \\
        --output outputs/x3d_heightmap/
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import shutil
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from ..csv_utils import discover_frames, load_frame, load_meta, load_terrain
from ...palette import Palette

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Visualisation constants (chunk size, LOD ranges, water surface lift,…) live
# next to the rendering code in ``static/js/config.js`` — keep them in one
# place so the Python side cannot drift out of sync with the browser side.
_NODATA      = -9999.0
_DEFAULT_RES = 5.0     # metres per PNG pixel — full source resolution

_TEMPLATE_DIR = Path(__file__).parent
_STATIC_DIR   = _TEMPLATE_DIR / "static"


# ---------------------------------------------------------------------------
# PNG encoders
# ---------------------------------------------------------------------------
def _encode_terrain_png(terrain_2d: np.ndarray) -> tuple[bytes, float, float]:
    """Encode (rows, cols) float32 heights as 8-bit grayscale PNG.

    Returns (png_bytes, min_h, max_h). Heights below ``_NODATA`` are clipped
    to the valid range so they do not skew the normalisation.
    """
    valid = terrain_2d[terrain_2d > _NODATA]
    min_h = float(valid.min()) if valid.size else 0.0
    max_h = float(valid.max()) if valid.size else 100.0
    if max_h == min_h:
        max_h = min_h + 1.0
    norm = np.clip((terrain_2d - min_h) / (max_h - min_h), 0.0, 1.0)
    img = Image.fromarray((norm * 255).astype(np.uint8), mode="L")
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), min_h, max_h


def _encode_flood_png(palette_2d: np.ndarray) -> bytes:
    """Encode (rows, cols) palette indices (0–5) as 8-bit grayscale PNG."""
    img = Image.fromarray(palette_2d.astype(np.uint8), mode="L")
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Palette loading
# ---------------------------------------------------------------------------
def _auto_detect_palette(csv_dir: Path) -> Path | None:
    for parent in csv_dir.parents:
        c = parent / "data" / "data_29_10_2024" / "color_palette.json"
        if c.exists():
            return c
    return None


def _load_state_colors(palette_path: Path | None) -> list[tuple[int, int, int]]:
    defaults = [
        (245, 222, 179),  # 0 dry
        (153, 204, 255),  # 1 very shallow
        (100, 150, 220),  # 2 low
        (30,  100, 200),  # 3 medium
        (0,    50, 180),  # 4 high
        (75,    0, 130),  # 5 extreme
    ]
    if palette_path is None or not palette_path.exists():
        return defaults
    try:
        data = json.loads(palette_path.read_text(encoding="utf-8"))
        fr = data.get("layers", {}).get("flood_risk", [])
        if fr:
            return [(e["rgba"][0], e["rgba"][1], e["rgba"][2])
                    for e in sorted(fr, key=lambda e: e["value"])]
        x3d = data.get("x3d", {}).get("state_colors", [])
        if x3d:
            return [(int(r * 255), int(g * 255), int(b * 255)) for r, g, b in x3d]
    except Exception:
        pass
    return defaults


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def _state_color_strings(state_colors: list[tuple[int, int, int]]) -> list[str]:
    """Convert RGB 0-255 tuples into the "r g b" floats X3D expects."""
    return [f"{r/255:.2f} {g/255:.2f} {b/255:.2f}" for r, g, b in state_colors]


def _viewpoints(map_w: float, map_d: float, max_h: float) -> dict:
    """Return position/orientation strings for the three camera presets."""
    cam_h = max(max_h * 3.0, map_d * 0.3)
    return {
        "overview": {
            "pos":    f"{map_w/2:.0f} {cam_h:.0f} {map_d + map_d * 0.4:.0f}",
            "orient": "1 0 0 -0.5",
        },
        "cenital": {
            "pos":    f"{map_w/2:.0f} {cam_h * 2:.0f} {map_d/2:.0f}",
            "orient": "1 0 0 -1.5708",
        },
        "lateral": {
            "pos":    f"{map_w/2:.0f} {cam_h * 0.35:.0f} {map_d * 2.2:.0f}",
            "orient": "0 0 0 1",
        },
    }


def _read_static_asset(relative: str) -> str:
    return (_STATIC_DIR / relative).read_text(encoding="utf-8")


def _state_names_from_colors(
    palette_path: Path | None,
    state_colors: list[tuple[int, int, int]],
) -> list[str]:
    """Return label strings matching the order of state_colors."""
    defaults = ["Dry", "Muy somero", "Profundidad baja", "Profundidad media",
                "Profundidad alta", "Profundidad extrema"]
    if palette_path is None or not palette_path.exists():
        return defaults[:len(state_colors)]
    try:
        data = json.loads(palette_path.read_text(encoding="utf-8"))
        fr = data.get("layers", {}).get("flood_risk", [])
        if fr:
            return [e["label"] for e in sorted(fr, key=lambda e: e["value"])]
    except Exception:
        pass
    return defaults[:len(state_colors)]


def generate_player(
    *,
    png_cols: int,
    png_rows: int,
    png_res_m: float,
    orig_cols: int,
    orig_rows: int,
    cell_size_m: float,
    min_h: float,
    max_h: float,
    terrain_b64: str,
    frame_names: list[str],
    state_colors: list[tuple[int, int, int]] | None = None,
    palette_path: Path | None = None,
    palette: Palette | None = None,
) -> str:
    """Render the player HTML by combining the Jinja2 template, CSS and runtime config.

    Only values that vary across simulation runs are injected here. Compile-time
    constants (chunk size, LOD ranges, water lift) live in ``static/js/config.js``.

    Color/label data comes from a single source, in order of preference:
      - ``palette``: a resolved Palette (the live MQTT pipeline always provides one)
      - ``state_colors``/``palette_path``: legacy file-based path used by the offline CLI
    """
    map_w = orig_cols * cell_size_m
    map_d = orig_rows * cell_size_m

    if palette is not None:
        state_color_strings = palette.rgb_strings()
        state_names = palette.labels()
    else:
        state_colors = state_colors or []
        state_color_strings = _state_color_strings(state_colors)
        state_names = _state_names_from_colors(palette_path, state_colors)

    config = {
        "pngCols":     png_cols,
        "pngRows":     png_rows,
        "pngRes":      png_res_m,
        "mapW":        map_w,
        "mapD":        map_d,
        "minH":        min_h,
        "maxH":        max_h,
        "stateColors": state_color_strings,
        "floodFrames": frame_names,
        "terrainSrc":  f"data:image/png;base64,{terrain_b64}",
    }

    viewpoints = _viewpoints(map_w, map_d, max_h)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),  # raw HTML output
        keep_trailing_newline=True,
    )
    template = env.get_template("template.html.j2")

    return template.render(
        inlined_css=_read_static_asset("css/style.css"),
        config_json=json.dumps(config),
        viewpoints=viewpoints,
        n_frames=len(frame_names),
        rows=orig_rows,
        cols=orig_cols,
        cell_size=f"{cell_size_m:.4f}",
        frame_count=len(frame_names),
        state_names=state_names,
    )


def copy_js_assets(output_dir: Path) -> None:
    """Copy the ES module tree from ``static/js/`` to ``<output_dir>/js/``.

    Wipes any pre-existing ``js/`` directory so stale modules are not left
    behind across regenerations.
    """
    src = _STATIC_DIR / "js"
    dst = output_dir / "js"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Generate X3D heightmap viewer from DanaSim CSV data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", required=True, help="Path to csv_data/ directory")
    parser.add_argument("--output", default="outputs/x3d_heightmap",
                        help="Output directory")
    parser.add_argument("--resolution", type=float, default=_DEFAULT_RES,
                        help="PNG resolution in metres (downsampling factor for terrain and flood)")
    parser.add_argument("--frames", type=int, default=None,
                        help="Limit to first N frames")
    parser.add_argument("--palette", default=None,
                        help="Path to color_palette.json (auto-detected if omitted)")
    args = parser.parse_args(argv)

    csv_dir    = Path(args.csv).resolve()
    if not csv_dir.exists():
        log.error("csv_dir not found: %s", csv_dir)
        return 1
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    meta       = load_meta(csv_dir)
    rows, cols = meta["rows"], meta["cols"]
    cell_size  = meta["cell_size_m"]
    factor     = max(1, round(args.resolution / cell_size))
    actual_res = cell_size * factor
    log.info("Grid: %dx%d  cell_size=%.2fm  PNG res=%.1fm (downsample ×%d)",
             rows, cols, cell_size, actual_res, factor)

    terrain    = load_terrain(csv_dir)
    terrain_2d = np.where(
        terrain.reshape(rows, cols) < -9000.0, 0.0,
        terrain.reshape(rows, cols)
    ).astype(np.float32)
    terrain_dn = terrain_2d[::factor, ::factor]
    d_rows, d_cols = terrain_dn.shape
    log.info("Terrain PNG: %dx%d pixels", d_rows, d_cols)

    terrain_png, min_h, max_h = _encode_terrain_png(terrain_dn)
    log.info("Heights: min=%.2fm  max=%.2fm  PNG=%.1fKB",
             min_h, max_h, len(terrain_png) / 1024)
    terrain_b64 = base64.b64encode(terrain_png).decode("ascii")

    palette_path = Path(args.palette) if args.palette else _auto_detect_palette(csv_dir)
    state_colors = _load_state_colors(palette_path)
    log.info("State colors: %d states", len(state_colors))

    frame_paths = discover_frames(csv_dir)
    if args.frames is not None:
        frame_paths = frame_paths[: args.frames]
    if not frame_paths:
        log.error("No step_XXXXX.csv files found in %s", csv_dir)
        return 1

    flood_dir = output_dir / "flood"
    flood_dir.mkdir(parents=True, exist_ok=True)
    frame_names: list[str] = []

    for fp in frame_paths:
        step_name = fp.stem
        palette_grid, _ = load_frame(fp, rows, cols)
        palette_dn = palette_grid[::factor, ::factor]
        flood_png  = _encode_flood_png(palette_dn)
        (flood_dir / f"{step_name}.png").write_bytes(flood_png)
        frame_names.append(step_name)
        log.info("Frame %s — flood PNG %.1fKB", step_name, len(flood_png) / 1024)

    player_html = generate_player(
        png_cols=d_cols,
        png_rows=d_rows,
        png_res_m=actual_res,
        orig_cols=cols,
        orig_rows=rows,
        cell_size_m=cell_size,
        min_h=min_h,
        max_h=max_h,
        terrain_b64=terrain_b64,
        frame_names=frame_names,
        state_colors=state_colors,
        palette_path=palette_path,
    )
    player_path = output_dir / "player.html"
    player_path.write_text(player_html, encoding="utf-8")
    log.info("Player: %s  (%.1fKB)", player_path, player_path.stat().st_size / 1024)

    copy_js_assets(output_dir)
    log.info("JS modules copied to: %s", output_dir / "js")

    log.info("Done — %d frames processed", len(frame_names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
