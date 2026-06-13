from __future__ import annotations

import numpy as np

from .base import DepthProvider


class DirectDepthProvider(DepthProvider):
    """Returns real water depths (metres) received directly from the simulator.

    Requires update_from_grid() to be called after each FrameEnd so the
    internal reference stays current.
    """

    def __init__(self) -> None:
        self._water_depths_m: np.ndarray | None = None

    def setup(self, rows: int, cols: int) -> None:
        self._water_depths_m = np.zeros((rows, cols), dtype=np.float32)

    def update_from_grid(self, water_depths_m: np.ndarray) -> None:
        self._water_depths_m = water_depths_m

    def get_water_depths(self, palette_grid: np.ndarray) -> np.ndarray:
        if self._water_depths_m is None:
            raise RuntimeError("DirectDepthProvider.setup() must be called before get_water_depths()")
        return self._water_depths_m
