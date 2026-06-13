"""Tiled LOD X3D serializer.

Splits the simulation grid into fixed-size chunks. Each chunk is rendered as
an X3D <LOD> node with multiple resolution levels, allowing the browser to
display high detail up close and switch to coarser meshes at distance — without
ever rendering all 52M vertices simultaneously.

Math helpers (_scale_z, _sanitize, _compute_viewpoint) are inlined from
serializer.py to keep this class fully standalone with no coupling to X3DSerializer.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np

from ..base import FrameData, GridMeta
from .colors import X3DColorScheme

_WATER_MIN_THRESHOLD = 0.0005   # metres — matches serializer.py
_NODATA_THRESHOLD    = -500.0   # values below this are treated as nodata


class TiledX3DSerializer:
    """Tiled LOD X3D serializer.

    Call configure() once, then serialize() per frame and generate_player() at end.

    serialize() returns (html_str, frame_token) where frame_token is a JSON string
    encoding per-chunk height/color strings keyed by "{chunk_row}_{chunk_col}_{level}".
    generate_player() accepts a list of those tokens and produces an animated player.

    Config (all optional — defaults match NOTES.md reserved vars):
        chunk_size      int     cells per chunk side (default 256)
        lod_subsamples  list    subsample factor per LOD level, coarsest last (default [1,4,16])
        lod_ranges      list    normalized-space distances for LOD transitions (default [5000,20000])
    """

    def configure(
        self,
        meta: GridMeta,
        colors: X3DColorScheme | None = None,
        chunk_size: int = 256,
        lod_subsamples: list[int] | None = None,
        lod_ranges: list[float] | None = None,
        wet_mask: np.ndarray | None = None,
    ) -> None:
        if meta.rows == 0 or meta.cols == 0:
            raise ValueError("TiledX3DSerializer: rows and cols must be > 0")
        self._meta = meta
        self._colors = colors or X3DColorScheme()
        self._chunk_size = max(1, chunk_size)
        self._lod_subsamples: list[int] = lod_subsamples if lod_subsamples is not None else [1, 4, 16]
        self._lod_ranges: list[float] = lod_ranges if lod_ranges is not None else [5000.0, 20000.0]

        rows, cols = meta.rows, meta.cols
        cs = self._chunk_size
        self._n_chunks_r = math.ceil(rows / cs)
        self._n_chunks_c = math.ceil(cols / cs)

        # Normalization factor — same formula as serializer.py
        # Uses full grid physical extents so coordinates are consistent across chunks
        grid_w = cols * meta.cell_size_m
        grid_h = rows * meta.cell_size_m
        self._norm = max(grid_w, grid_h) / 1000.0

        self._scale = self._scale_z()

        # Determine which tiles ever contain water across all frames.
        # Dry tiles use only the coarsest LOD level, saving most of the file size.
        # wet_mask is a flat boolean array of shape (rows*cols,); None means treat all tiles as wet.
        if wet_mask is not None:
            wet_2d = wet_mask.reshape(rows, cols)
            self._wet_tiles: set[tuple[int, int]] | None = set()
            for cr in range(self._n_chunks_r):
                for cc in range(self._n_chunks_c):
                    r0, r1 = cr * cs, min((cr + 1) * cs, rows)
                    c0, c1 = cc * cs, min((cc + 1) * cs, cols)
                    if wet_2d[r0:r1, c0:c1].any():
                        self._wet_tiles.add((cr, cc))
        else:
            self._wet_tiles = None  # all tiles treated as wet

        # Pre-compute terrain chunks per LOD level to avoid recomputing every frame.
        # Dry tiles only need the coarsest level.
        coarsest_level = len(self._lod_subsamples) - 1
        self._terrain_chunks: dict[int, dict[tuple[int, int], np.ndarray]] = {}
        for level, s in enumerate(self._lod_subsamples):
            self._terrain_chunks[level] = {}
            for cr in range(self._n_chunks_r):
                for cc in range(self._n_chunks_c):
                    is_wet = self._wet_tiles is None or (cr, cc) in self._wet_tiles
                    if is_wet or level == coarsest_level:
                        self._terrain_chunks[level][(cr, cc)] = self._extract_terrain_chunk(cr, cc, s)

        self._configured = True
        log = logging.getLogger(__name__)
        n_wet = len(self._wet_tiles) if self._wet_tiles is not None else self._n_chunks_r * self._n_chunks_c
        log.info(
            "TiledX3DSerializer ready — grid %dx%d  chunk %d  levels %s  "
            "tiles %dx%d=%d  wet=%d  norm=%.4f  scale=%.4f",
            rows, cols, self._chunk_size, self._lod_subsamples,
            self._n_chunks_r, self._n_chunks_c,
            self._n_chunks_r * self._n_chunks_c, n_wet,
            self._norm, self._scale,
        )

    def serialize(self, frame: FrameData) -> tuple[str, str]:
        """Return (html_document, frame_token_json) for this frame."""
        self._assert_configured()
        meta = self._meta
        rows, cols = meta.rows, meta.cols

        # Viewpoint computed from full-grid overview
        cs = self._chunk_size
        grid_w = cols * meta.cell_size_m / self._norm
        grid_h = rows * meta.cell_size_m / self._norm
        terrain_flat = (meta.terrain_heights.reshape(rows, cols)[::cs, ::cs].flatten()
                        if meta.terrain_heights is not None
                        else np.zeros(0, dtype=np.float32))
        max_h_n = float(self._sanitize(terrain_flat.astype(np.float32)).max()) * self._scale / self._norm if terrain_flat.size else 0.0
        viewpoint, orientation = self._compute_viewpoint(grid_w, grid_h, max_h_n)

        chunk_nodes = []
        token_dict: dict[str, list[str]] = {}

        for cr in range(self._n_chunks_r):
            for cc in range(self._n_chunks_c):
                node_xml, chunk_tokens = self._build_chunk(frame, cr, cc)
                chunk_nodes.append(node_xml)
                token_dict.update(chunk_tokens)

        r, g, b = self._colors.sky
        sky_str = f"{r:.2f} {g:.2f} {b:.2f}"
        chunks_xml = "\n".join(chunk_nodes)

        scene = f"""<x3d>
  <scene>
    <background skyColor="{sky_str}"></background>
    <Viewpoint position="{viewpoint}" orientation="{orientation}" description="Overview"></Viewpoint>
    <NavigationInfo type='"EXAMINE" "ANY"'></NavigationInfo>
{chunks_xml}
  </scene>
</x3d>"""

        html = self._wrap_html(scene)
        token_json = json.dumps(token_dict, separators=(",", ":"))
        return html, token_json

    def generate_player(self, frame_tokens: list[str]) -> str:
        """Generate animated player HTML from a list of frame tokens."""
        self._assert_configured()
        meta = self._meta
        rows, cols = meta.rows, meta.cols

        # Build initial scene from a dry frame so all chunk DEF nodes exist in the DOM.
        # JavaScript will call setFrame(0) on load to apply the actual first frame.
        first_frame = FrameData(
            palette_grid=np.zeros((rows, cols), dtype=np.uint8),
            water_depths=np.zeros((rows, cols), dtype=np.float32),
        )
        first_html_full, _ = self.serialize(first_frame)

        # Extract the <x3d>...</x3d> part for embedding in the player
        x3d_start = first_html_full.find("<x3d>")
        x3d_end = first_html_full.find("</x3d>") + len("</x3d>")
        scene_xml = first_html_full[x3d_start:x3d_end] if x3d_start != -1 else ""

        n_frames = len(frame_tokens)
        frames_js = ",\n  ".join(frame_tokens)

        cs = self._chunk_size
        spacing_n = meta.cell_size_m / self._norm
        n_chunks_r = self._n_chunks_r
        n_chunks_c = self._n_chunks_c

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>DanaSim LOD Player — {rows}x{cols}</title>
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
  <!-- rows={rows} cols={cols} cell_size={meta.cell_size_m:.4f}m frames={n_frames}
       tiles={n_chunks_r}x{n_chunks_c}  lod_levels={len(self._lod_subsamples)} -->
  <div id="viewport">
    <x3d-canvas>
{scene_xml}
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
      const fd = simFrames[current];
      for (const [key, [h, c]] of Object.entries(fd)) {{
        const parts = key.split("_");
        const cr = parts[0], cc = parts[1], level = parts[2];
        const grid = document.querySelector(`ElevationGrid[DEF='Chunk_${{cr}}_${{cc}}_L${{level}}']`);
        if (grid) grid.setAttribute("height", h);
        const col = document.querySelector(`Color[DEF='Chunk_${{cr}}_${{cc}}_L${{level}}_Color']`);
        if (col) col.setAttribute("color", c);
      }}
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

    def serialize_empty_frame(self) -> tuple[str, str]:
        """Convenience: serialize a fully dry frame (for player initialization)."""
        meta = self._meta
        frame = FrameData(
            palette_grid=np.zeros((meta.rows, meta.cols), dtype=np.uint8),
            water_depths=np.zeros((meta.rows, meta.cols), dtype=np.float32),
        )
        return self.serialize(frame)

    # ------------------------------------------------------------------
    # Private — chunk building
    # ------------------------------------------------------------------

    def _build_chunk(
        self, frame: FrameData, cr: int, cc: int
    ) -> tuple[str, dict[str, list[str]]]:
        """Build <Transform><LOD>...</LOD></Transform> XML for one chunk.

        Returns (xml_string, token_dict) where token_dict maps
        "{cr}_{cc}_{level}" -> [heights_str, colors_str].
        """
        meta = self._meta
        cs = self._chunk_size
        norm = self._norm
        scale = self._scale

        # Physical offset of this chunk's origin in normalised X3D coords
        tx = cc * cs * meta.cell_size_m / norm
        tz = cr * cs * meta.cell_size_m / norm

        range_attr = " ".join(str(r) for r in self._lod_ranges)
        shapes = []
        token_dict: dict[str, list[str]] = {}

        is_wet = self._wet_tiles is None or (cr, cc) in self._wet_tiles
        coarsest_level = len(self._lod_subsamples) - 1

        for level, s in enumerate(self._lod_subsamples):
            # Dry tiles reuse the coarsest level data for all LOD slots so the
            # DOM structure stays uniform while keeping the tile data tiny.
            if not is_wet and level != coarsest_level:
                s = self._lod_subsamples[coarsest_level]
                terrain_chunk = self._terrain_chunks[coarsest_level][(cr, cc)]
            else:
                terrain_chunk = self._terrain_chunks[level][(cr, cc)]

            # Water depths for this chunk at this subsample
            r0 = cr * cs
            c0 = cc * cs
            r1 = min(r0 + cs, meta.rows)
            c1 = min(c0 + cs, meta.cols)
            water_slice = frame.water_depths[r0:r1, c0:c1][::s, ::s].flatten().astype(np.float32)
            water_slice = self._sanitize(water_slice)
            wet = water_slice >= _WATER_MIN_THRESHOLD
            surface = terrain_chunk.copy()
            surface[wet] += water_slice[wet] * scale / norm  # terrain already normalised

            heights_str = " ".join(f"{v:.4f}" for v in surface.tolist())

            # Colors
            palette_slice = frame.palette_grid[r0:r1, c0:c1][::s, ::s].flatten().astype(np.int32)
            colors_arr = np.array(self._colors.state_colors, dtype=np.float32)
            palette_slice = np.clip(palette_slice, 0, len(colors_arr) - 1)
            vertex_colors = colors_arr[palette_slice].reshape(-1)
            colors_str = " ".join(f"{v:.2f}" for v in vertex_colors.tolist())

            chunk_rows = len(range(0, r1 - r0, s))
            chunk_cols = len(range(0, c1 - c0, s))
            spacing_n = meta.cell_size_m * s / norm

            grid_def = f"Chunk_{cr}_{cc}_L{level}"
            color_def = f"Chunk_{cr}_{cc}_L{level}_Color"

            shapes.append(f"""    <Shape>
      <Appearance>
        <Material ambientIntensity="1" diffuseColor="1 1 1" specularColor="0 0 0"/>
      </Appearance>
      <ElevationGrid DEF="{grid_def}" xDimension="{chunk_cols}" zDimension="{chunk_rows}"
        xSpacing="{spacing_n:.4f}" zSpacing="{spacing_n:.4f}"
        height="{heights_str}"
        colorPerVertex="true" solid="false">
        <Color DEF="{color_def}" color="{colors_str}"/>
      </ElevationGrid>
    </Shape>""")

            token_dict[f"{cr}_{cc}_{level}"] = [heights_str, colors_str]

        shapes_xml = "\n".join(shapes)
        lod_xml = f"""  <Transform translation="{tx:.4f} 0.0 {tz:.4f}">
    <LOD range="{range_attr}">
{shapes_xml}
    </LOD>
  </Transform>"""

        return lod_xml, token_dict

    def _extract_terrain_chunk(self, cr: int, cc: int, s: int) -> np.ndarray:
        """Extract, scale, and normalise a terrain chunk. Returns flat float32 array."""
        meta = self._meta
        cs = self._chunk_size
        r0 = cr * cs
        c0 = cc * cs
        r1 = min(r0 + cs, meta.rows)
        c1 = min(c0 + cs, meta.cols)

        if meta.terrain_heights is not None and meta.terrain_heights.size == meta.rows * meta.cols:
            raw = meta.terrain_heights.reshape(meta.rows, meta.cols)[r0:r1, c0:c1][::s, ::s].flatten().astype(np.float32)
            raw = np.where(raw < _NODATA_THRESHOLD, 0.0, raw)
        else:
            n = len(range(0, r1 - r0, s)) * len(range(0, c1 - c0, s))
            raw = np.zeros(n, dtype=np.float32)

        return self._sanitize(raw) * self._scale / self._norm

    # ------------------------------------------------------------------
    # Private — math helpers (inlined from serializer.py)
    # ------------------------------------------------------------------

    def _scale_z(self) -> float:
        """Vertical exaggeration so terrain height ≈ 30% of shorter grid side.
        Inlined from X3DSerializer._scale_z in serializer.py.
        """
        meta = self._meta
        log = logging.getLogger(__name__)
        if meta.terrain_heights is None:
            return 1.0
        raw = meta.terrain_heights.reshape(-1).astype(np.float32)
        valid = raw[raw > _NODATA_THRESHOLD]
        if valid.size == 0:
            return 1.0
        terrain_range = float(valid.max() - valid.min())
        if terrain_range < 0.01:
            log.warning("_scale_z: terrain_range=%.4f too small, using scale=1.0", terrain_range)
            return 1.0
        min_dim = min(meta.rows * meta.cell_size_m, meta.cols * meta.cell_size_m)
        return (min_dim * 0.30) / terrain_range

    def _sanitize(self, values: np.ndarray) -> np.ndarray:
        """Clamp NaN/Inf to safe values. Inlined from X3DSerializer._sanitize."""
        out = values.copy()
        out = np.where(np.isnan(out), 0.0, out)
        out = np.where(np.isposinf(out), 1000.0, out)
        out = np.where(np.isneginf(out), -1000.0, out)
        return np.clip(out, -1000.0, 10000.0)

    def _compute_viewpoint(self, grid_w: float, grid_h: float, max_height: float = 0.0) -> tuple[str, str]:
        """Compute camera position and orientation. Inlined from X3DSerializer._compute_viewpoint."""
        cx = grid_w * 0.5
        cz = grid_h * 0.5
        max_dim = max(grid_w, grid_h)
        cam_x = cx
        cam_y = max(max_height * 1.5, max_dim * 0.05)
        cam_z = cz + max_dim * 0.8
        angle = -math.atan2(cam_y, max_dim * 0.8)
        return f"{cam_x:.2f} {cam_y:.2f} {cam_z:.2f}", f"1 0 0 {angle:.3f}"

    def _wrap_html(self, scene: str) -> str:
        meta = self._meta
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>DanaSim LOD — {meta.rows}x{meta.cols} grid</title>
  <script src="https://cdn.jsdelivr.net/npm/x_ite@12.1.4/dist/x_ite.min.js"></script>
  <style>
    html, body {{ margin: 0; height: 100%; background: #1a1a2e; }}
    x3d-canvas {{ width: 100vw; height: 100vh; display: block; }}
  </style>
</head>
<body>
  <!-- rows={meta.rows} cols={meta.cols} cell_size={meta.cell_size_m:.4f}m
       tiles={self._n_chunks_r}x{self._n_chunks_c}  lod_levels={len(self._lod_subsamples)} -->
  <x3d-canvas>
{scene}
  </x3d-canvas>
</body>
</html>
"""

    def _assert_configured(self) -> None:
        if not getattr(self, "_configured", False):
            raise RuntimeError("TiledX3DSerializer.configure() must be called before use")
