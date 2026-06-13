from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class DepthProvider(ABC):
    @abstractmethod
    def setup(self, rows: int, cols: int) -> None: ...

    @abstractmethod
    def get_water_depths(self, palette_grid: np.ndarray) -> np.ndarray: ...

    def update_from_grid(self, water_depths_m: np.ndarray) -> None:
        """No-op by default. Override to receive the real float depth grid after each frame."""
        pass
