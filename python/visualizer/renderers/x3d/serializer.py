from __future__ import annotations

import logging
import math

import numpy as np

from ..base import FrameData, GridMeta
from .colors import X3DColorScheme

_WATER_MIN_THRESHOLD = 0.0005  # metres — filter visual noise
_NODATA_THRESHOLD = -500.0     # values below this are treated as nodata


class X3DSerializer:
    """Pure string serialization of a simulation snapshot to an X3D/HTML document.

    No filesystem access — fully unit-testable.
    Call configure() once after init, then serialize() per frame.

    Single ElevationGrid approach:
      height      = topo_bathy + water_depth  (where flooded)
                  = topo_bathy               (where dry)
      colorIndex  = palette state (0–5) per vertex
      Color node  = 6 fixed RGB entries, one per state
    """

    def configure(self, meta: GridMeta, colors: X3DColorScheme | None = None,
                  subsample: int = 1) -> None:
        if meta.rows == 0 or meta.cols == 0:
            raise ValueError("X3DSerializer: rows and cols must be > 0")
        self._meta = meta
        self._colors = colors or X3DColorScheme()
        self._subsample = max(1, subsample)
        s = self._subsample
        self._rows_s = len(range(0, meta.rows, s))
        self._cols_s = len(range(0, meta.cols, s))
        self._spacing_s = meta.cell_size_m * s
        self._configured = True

    def serialize(self, frame: FrameData) -> tuple[str, tuple[str, str]]:
        """Return (html_document, (heights_str, colors_str)) for this frame.

        The second element is kept separate so the renderer can accumulate it
        for the animation player.
        """
        if not getattr(self, "_configured", False):
            raise RuntimeError("X3DSerializer.configure() must be called before serialize()")

        meta = self._meta
        rows, cols = self._rows_s, self._cols_s
        spacing = self._spacing_s

        scale = self._scale_z()
        surface = self._get_surface(frame, scale)
        colors_str = self._get_colors_str(frame)

        grid_w = cols * spacing
        grid_h = rows * spacing
        norm = max(grid_w, grid_h) / 1000.0
        spacing_n = spacing / norm
        surface_n = surface / norm
        max_h_n = float(surface_n.max()) if surface_n.size else 0.0
        viewpoint, orientation = self._compute_viewpoint(grid_w / norm, grid_h / norm, max_h_n)

        heights_str = self._heights_to_str(surface_n)

        scene = self._build_scene(cols, rows, spacing_n, viewpoint, orientation,
                                  heights_str, colors_str)
        return self._wrap_html(scene, meta), (heights_str, colors_str)

    def generate_player(self, frames: list[tuple[str, str]]) -> str:
        """Generate a single HTML player that animates all frames."""
        if not getattr(self, "_configured", False):
            raise RuntimeError("X3DSerializer.configure() must be called before generate_player()")

        meta = self._meta
        rows, cols = self._rows_s, self._cols_s
        spacing = self._spacing_s

        scale = self._scale_z()
        terrain = self._get_terrain_scaled(scale)
        grid_w = cols * spacing
        grid_h = rows * spacing
        norm = max(grid_w, grid_h) / 1000.0
        spacing_n = spacing / norm
        max_h_n = float(terrain.max()) / norm if terrain.size else 0.0
        viewpoint, orientation = self._compute_viewpoint(grid_w / norm, grid_h / norm, max_h_n)

        first_h, first_c = frames[0] if frames else ("", "")
        scene = self._build_scene(cols, rows, spacing_n, viewpoint, orientation,
                                  first_h, first_c,
                                  surface_def="SurfaceGrid", color_def="SurfaceColor")

        n_frames = len(frames)
        frames_js = ",\n  ".join(
            f'{{h:"{h}",c:"{c}"}}'
            for h, c in frames
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>DanaSim Player — {rows}x{cols}</title>
  <script src="https://cdn.jsdelivr.net/npm/x_ite@12.1.4/dist/x_ite.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #1a1a2e; color: #e0e0e0; font-family: sans-serif;
           display: flex; flex-direction: column; height: 100vh; }}
    #viewport {{ flex: 1; min-height: 0; overflow: hidden; }}
    x3d-canvas {{ width: 100%; height: 100%; display: block; }}
    #controls {{
      padding: 10px 16px; background: #16213e;
      display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
      border-top: 1px solid #0f3460;
    }}
    #controls button {{
      background: #0f3460; color: #e0e0e0; border: 1px solid #1a6ea8;
      border-radius: 4px; padding: 5px 14px; cursor: pointer; font-size: 14px;
    }}
    #controls button:hover {{ background: #1a6ea8; }}
    #slider {{ flex: 1; min-width: 120px; accent-color: #1a6ea8; }}
    #speed  {{ width: 80px; accent-color: #1a6ea8; }}
    label {{ font-size: 12px; color: #a0a0c0; }}
    #frame-label {{ font-size: 13px; min-width: 80px; }}
  </style>
</head>
<body>
  <!-- rows={rows} cols={cols} cell_size={spacing:.4f}m  frames={n_frames} -->
  <div id="viewport">
    <x3d-canvas>
{scene}
    </x3d-canvas>
  </div>
  <div id="controls">
    <button id="prevBtn">&#9664;</button>
    <button id="playBtn">&#9654; Play</button>
    <button id="nextBtn">&#9654;&#9654;</button>
    <input id="slider" type="range" min="0" max="{n_frames - 1}" value="0"/>
    <span id="frame-label">Frame 0 / {n_frames - 1}</span>
    <label>Speed <input id="speed" type="range" min="100" max="2000" value="600" step="100"/></label>
  </div>

  <script>
    const simFrames = [
  {frames_js}
    ];

    let current = 0;
    let playing = false;
    let timer = null;

    function setFrame(i) {{
      current = ((i % simFrames.length) + simFrames.length) % simFrames.length;
      const grid = document.querySelector("ElevationGrid[DEF='SurfaceGrid']");
      if (grid) grid.setAttribute("height", simFrames[current].h);
      const colorNode = document.querySelector("Color[DEF='SurfaceColor']");
      if (colorNode) colorNode.setAttribute("color", simFrames[current].c);
      document.getElementById("slider").value = current;
      document.getElementById("frame-label").textContent =
        "Frame " + current + " / " + (simFrames.length - 1);
    }}

    function startPlay() {{
      const ms = parseInt(document.getElementById("speed").value);
      timer = setInterval(() => setFrame(current + 1), ms);
      playing = true;
      document.getElementById("playBtn").textContent = "⏸ Pause";
    }}

    function stopPlay() {{
      clearInterval(timer);
      playing = false;
      document.getElementById("playBtn").textContent = "▶ Play";
    }}

    document.getElementById("playBtn").addEventListener("click", () => {{
      playing ? stopPlay() : startPlay();
    }});
    document.getElementById("prevBtn").addEventListener("click", () => {{
      stopPlay(); setFrame(current - 1);
    }});
    document.getElementById("nextBtn").addEventListener("click", () => {{
      stopPlay(); setFrame(current + 1);
    }});
    document.getElementById("slider").addEventListener("input", e => {{
      stopPlay(); setFrame(parseInt(e.target.value));
    }});
    document.getElementById("speed").addEventListener("change", () => {{
      if (playing) {{ stopPlay(); startPlay(); }}
    }});

    document.querySelector("x3d-canvas").addEventListener("load", () => setFrame(0));
  </script>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_surface(self, frame: FrameData, scale: float) -> np.ndarray:
        """Single surface: terrain where dry, terrain+water where flooded."""
        s = self._subsample
        terrain = self._get_terrain_scaled(scale)
        water = self._sanitize(frame.water_depths[::s, ::s].flatten().astype(np.float32))
        wet = water >= _WATER_MIN_THRESHOLD
        surface = terrain.copy()
        surface[wet] += water[wet] * scale
        return surface

    def _get_colors_str(self, frame: FrameData) -> str:
        """Full per-vertex RGB string for the Color node."""
        s = self._subsample
        indices = frame.palette_grid[::s, ::s].flatten().astype(np.int32)
        colors_arr = np.array(self._colors.state_colors, dtype=np.float32)
        indices = np.clip(indices, 0, len(colors_arr) - 1)
        vertex_colors = colors_arr[indices]  # (N, 3)
        flat = vertex_colors.reshape(-1)
        return " ".join(f"{v:.2f}" for v in flat)

    def _get_terrain_scaled(self, scale: float) -> np.ndarray:
        meta = self._meta
        s = self._subsample
        log = logging.getLogger(__name__)
        rows, cols = meta.rows, meta.cols
        if meta.terrain_heights is not None and meta.terrain_heights.size == rows * cols:
            raw = meta.terrain_heights.reshape(rows, cols)[::s, ::s].flatten().astype(np.float32)
            nodata_count = int((raw < _NODATA_THRESHOLD).sum())
            if nodata_count:
                log.debug("terrain: replacing %d nodata cells (< %.0f) with 0", nodata_count, _NODATA_THRESHOLD)
            raw = np.where(raw < _NODATA_THRESHOLD, 0.0, raw)
        else:
            if meta.terrain_heights is None:
                log.warning("terrain_heights is None — rendering flat terrain")
            else:
                log.warning("terrain_heights size %d != grid %d*%d=%d — rendering flat terrain",
                            meta.terrain_heights.size, rows, cols, rows * cols)
            raw = np.zeros(self._rows_s * self._cols_s, dtype=np.float32)
        result = self._sanitize(raw) * scale
        log.info("terrain scaled: min=%.2f max=%.2f scale=%.4f", float(result.min()), float(result.max()), scale)
        return result

    def _scale_z(self) -> float:
        """Vertical exaggeration so terrain height ≈ 10% of the shorter grid side."""
        meta = self._meta
        log = logging.getLogger(__name__)
        if meta.terrain_heights is None:
            log.warning("_scale_z: terrain_heights is None, using scale=1.0")
            return 1.0
        raw = meta.terrain_heights.reshape(-1).astype(np.float32)
        # Exclude nodata values from range calculation
        valid = raw[raw > _NODATA_THRESHOLD]
        log.info("_scale_z: total=%d valid=%d nodata=%d raw_min=%.2f raw_max=%.2f",
                 raw.size, valid.size, raw.size - valid.size,
                 float(raw.min()), float(raw.max()))
        if valid.size == 0:
            return 1.0
        terrain_range = float(valid.max() - valid.min())
        if terrain_range < 0.01:
            log.warning("_scale_z: terrain_range=%.4f too small, using scale=1.0", terrain_range)
            return 1.0
        min_dim = min(meta.rows * meta.cell_size_m, meta.cols * meta.cell_size_m)
        scale = (min_dim * 0.30) / terrain_range
        log.info("_scale_z: terrain_range=%.2f min_dim=%.0fm scale=%.4f", terrain_range, min_dim, scale)
        return scale

    def _sanitize(self, values: np.ndarray) -> np.ndarray:
        out = values.copy()
        out = np.where(np.isnan(out), 0.0, out)
        out = np.where(np.isposinf(out), 1000.0, out)
        out = np.where(np.isneginf(out), -1000.0, out)
        return np.clip(out, -1000.0, 10000.0)

    def _heights_to_str(self, values: np.ndarray) -> str:
        return " ".join(f"{v:.4f}" for v in values)

    def _build_scene(self, cols: int, rows: int, spacing: float,
                     viewpoint: str, orientation: str,
                     heights_str: str, colors_str: str,
                     surface_def: str = "", color_def: str = "") -> str:
        def_attr = f' DEF="{surface_def}"' if surface_def else ""
        color_def_attr = f' DEF="{color_def}"' if color_def else ""
        r, g, b = self._colors.sky
        sky_str = f"{r:.2f} {g:.2f} {b:.2f}"
        return f"""<x3d>
  <scene>
    <background skyColor="{sky_str}"></background>
    <Viewpoint position="{viewpoint}" orientation="{orientation}" description="Overview"></Viewpoint>
    <NavigationInfo type='"EXAMINE" "ANY"'></NavigationInfo>
    <Shape>
      <Appearance>
        <Material ambientIntensity="1" diffuseColor="1 1 1" specularColor="0 0 0"/>
      </Appearance>
      <ElevationGrid{def_attr} xDimension="{cols}" zDimension="{rows}"
        xSpacing="{spacing:.4f}" zSpacing="{spacing:.4f}"
        height="{heights_str}"
        colorPerVertex="true"
        solid="false">
        <Color{color_def_attr} color="{colors_str}"/>
      </ElevationGrid>
    </Shape>
  </scene>
</x3d>"""

    def _compute_viewpoint(self, grid_w: float, grid_h: float, max_height: float = 0.0) -> tuple[str, str]:
        cx = grid_w * 0.5
        cz = grid_h * 0.5
        max_dim = max(grid_w, grid_h)
        cam_x = cx
        # Stay 1.5× above tallest terrain point, no higher than 20% of grid width
        cam_y = max(max_height * 1.5, max_dim * 0.05)
        cam_z = cz + max_dim * 0.8
        angle = -math.atan2(cam_y, max_dim * 0.8)
        return f"{cam_x:.2f} {cam_y:.2f} {cam_z:.2f}", f"1 0 0 {angle:.3f}"

    def _wrap_html(self, scene: str, meta: GridMeta) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>DanaSim — {meta.rows}x{meta.cols} grid</title>
  <script src="https://cdn.jsdelivr.net/npm/x_ite@12.1.4/dist/x_ite.min.js"></script>
  <style>
    html, body {{ margin: 0; height: 100%; background: #1a1a2e; }}
    x3d-canvas {{ width: 100vw; height: 100vh; display: block; }}
  </style>
</head>
<body>
  <!-- rows={meta.rows} cols={meta.cols} cell_size={meta.cell_size_m:.4f}m -->
  <x3d-canvas>
{scene}
  </x3d-canvas>
</body>
</html>
"""
