from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import numpy as np

from ..base import BaseRenderer, FrameData, GridMeta
from ...palette import Palette
from ...tools.x3d_player.generator import (
    _encode_terrain_png,
    _encode_flood_png,
    generate_player,
    copy_js_assets,
)

_NODATA = -9999.0


class X3DRenderer(BaseRenderer):
    """Writes flood PNGs directly during simulation.

    Generates player.html immediately at setup() with an empty frame list.
    Each new frame writes a PNG and updates flood/manifest.json so a live
    browser can poll for new frames without reloading the page.
    At close(), manifest is marked live=false to signal end of simulation.
    """

    def __init__(self, output_folder: str) -> None:
        self._output_dir = Path(output_folder) / "x3d_heightmap"
        self._flood_dir = self._output_dir / "flood"
        self._manifest_path = self._flood_dir / "manifest.json"
        self._logger = logging.getLogger(__name__)

        self._meta: GridMeta | None = None
        self._terrain_b64: str = ""
        self._min_h: float = 0.0
        self._max_h: float = 100.0
        self._png_rows: int = 0
        self._png_cols: int = 0
        self._frame_names: list[str] = []
        self._palette: Palette = Palette.default()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_manifest(self, *, live: bool) -> None:
        self._manifest_path.write_text(
            json.dumps({"frames": self._frame_names, "live": live}, indent=2),
            encoding="utf-8",
        )

    def _write_player(self) -> None:
        player_html = generate_player(
            png_cols=self._png_cols,
            png_rows=self._png_rows,
            png_res_m=self._meta.cell_size_m,
            orig_cols=self._meta.cols,
            orig_rows=self._meta.rows,
            cell_size_m=self._meta.cell_size_m,
            min_h=self._min_h,
            max_h=self._max_h,
            terrain_b64=self._terrain_b64,
            frame_names=self._frame_names,
            palette=self._palette,
        )
        (self._output_dir / "player.html").write_text(player_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # BaseRenderer interface
    # ------------------------------------------------------------------

    def setup(self, meta: GridMeta) -> None:
        self._meta = meta
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._flood_dir.mkdir(parents=True, exist_ok=True)

        self._palette = meta.palette

        terrain = meta.terrain_heights if meta.terrain_heights is not None \
            else np.zeros(meta.rows * meta.cols, dtype=np.float32)
        terrain_2d = np.where(
            terrain.reshape(meta.rows, meta.cols) < _NODATA,
            0.0,
            terrain.reshape(meta.rows, meta.cols),
        ).astype(np.float32)

        terrain_png, self._min_h, self._max_h = _encode_terrain_png(terrain_2d)
        self._terrain_b64 = base64.b64encode(terrain_png).decode("ascii")
        self._png_rows, self._png_cols = terrain_2d.shape

        # Generate player.html immediately so the browser can open it
        # before any frame arrives. manifest starts empty and live=true.
        copy_js_assets(self._output_dir)
        self._write_player()
        self._write_manifest(live=True)

        self._logger.info(
            "X3DRenderer ready — player: %s  heights: %.1f–%.1fm",
            self._output_dir / "player.html", self._min_h, self._max_h,
        )

    def save_snapshot(self, frame: FrameData, step_index: int) -> None:
        if self._meta is None:
            raise RuntimeError("X3DRenderer.setup() must be called before save_snapshot()")

        step_name = f"step_{step_index:05d}"
        palette_2d = frame.palette_grid.reshape(self._meta.rows, self._meta.cols)
        flood_png = _encode_flood_png(palette_2d)
        (self._flood_dir / f"{step_name}.png").write_bytes(flood_png)
        self._frame_names.append(step_name)
        self._write_manifest(live=True)
        self._logger.debug("Flood PNG saved: %s (%.1fKB)", step_name, len(flood_png) / 1024)

    def close(self) -> None:
        if self._meta is None:
            return
        self._write_manifest(live=False)
        self._logger.info(
            "Simulation ended — %d frames in %s",
            len(self._frame_names), self._output_dir,
        )
