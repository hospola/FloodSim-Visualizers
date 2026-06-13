from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import numpy as np

from ..base import BaseRenderer, FrameData, GridMeta


class CSVRenderer(BaseRenderer):
    """Saves sparse per-frame CSVs (flooded cells only) plus static terrain and metadata.

    Output layout under {output_folder}/csv_data/:
        meta.json           rows, cols, cell_size_m
        terrain.npy         float32 flat array of terrain heights (written once at setup)
        step_00000.csv      flooded cells for frame 0
        step_00001.csv      flooded cells for frame 1
        ...

    CSV format (UTF-8, comma-separated):
        # rows=5577 cols=9403 cell_size_m=5.0
        row,col,flood_risk

    Only flooded cells (flood_risk > 0) are written.
    Dry cells are omitted entirely (sparse representation).
    """

    def __init__(self, output_folder: str) -> None:
        self._output_folder = Path(output_folder) / "csv_data"
        self._meta: GridMeta | None = None
        self._frame_count = 0
        self._logger = logging.getLogger(__name__)

    def setup(self, meta: GridMeta) -> None:
        self._meta = meta
        self._output_folder.mkdir(parents=True, exist_ok=True)

        (self._output_folder / "meta.json").write_text(
            json.dumps({"rows": meta.rows, "cols": meta.cols, "cell_size_m": meta.cell_size_m}, indent=2),
            encoding="utf-8",
        )

        terrain = meta.terrain_heights if meta.terrain_heights is not None else np.zeros(meta.rows * meta.cols, dtype=np.float32)
        np.save(self._output_folder / "terrain.npy", terrain.astype(np.float32))

        self._logger.info(
            "CSVRenderer ready — output: %s  grid: %sx%s  cell: %.2fm",
            self._output_folder, meta.rows, meta.cols, meta.cell_size_m,
        )

    def save_snapshot(self, frame: FrameData, step_index: int) -> None:
        if self._meta is None:
            raise RuntimeError("CSVRenderer.setup() must be called before save_snapshot()")

        meta = self._meta
        path = self._output_folder / f"step_{step_index:05d}.csv"

        try:
            rows_idx, cols_idx = np.nonzero(frame.palette_grid > 0)
            with path.open("w", newline="", encoding="utf-8") as fh:
                fh.write(f"# rows={meta.rows} cols={meta.cols} cell_size_m={meta.cell_size_m}\n")
                writer = csv.writer(fh)
                writer.writerow(["row", "col", "flood_risk"])
                for r, c in zip(rows_idx.tolist(), cols_idx.tolist()):
                    writer.writerow([r, c, int(frame.palette_grid[r, c])])
            self._frame_count += 1
            self._logger.debug("CSV frame saved: %s  (%d wet cells)", path, len(rows_idx))
        except OSError as exc:
            self._logger.error("Failed to write CSV frame %s: %s", path, exc)

    def close(self) -> None:
        self._logger.info("CSVRenderer closed — %d frames in %s", self._frame_count, self._output_folder)
