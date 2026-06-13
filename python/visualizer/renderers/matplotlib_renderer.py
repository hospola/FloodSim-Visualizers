from __future__ import annotations

from ..visualizer import GridVisualizer
from .base import BaseRenderer, FrameData, GridMeta


class MatplotlibRenderer(BaseRenderer):
    def __init__(self, output_folder: str) -> None:
        self._output_folder = output_folder
        self._visualizer: GridVisualizer | None = None

    def setup(self, meta: GridMeta) -> None:
        self._visualizer = GridVisualizer(output_folder=self._output_folder, palette=meta.palette)

    def save_snapshot(self, frame: FrameData, step_index: int) -> None:
        if self._visualizer is None:
            raise RuntimeError("MatplotlibRenderer.setup() must be called before save_snapshot()")
        self._visualizer.save_snapshot(frame.palette_grid, step_index)

    def close(self) -> None:
        if self._visualizer is not None:
            self._visualizer.close()
