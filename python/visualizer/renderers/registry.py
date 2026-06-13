from __future__ import annotations

from .base import BaseRenderer
from .csv.csv_renderer import CSVRenderer
from .matplotlib_renderer import MatplotlibRenderer
from .x3d.x3d_renderer import X3DRenderer
from ..depth_providers.base import DepthProvider
from ..depth_providers.palette import PaletteDepthProvider
from ..depth_providers.direct import DirectDepthProvider

_RENDERER_REGISTRY: dict[str, type[BaseRenderer]] = {
    "2d": MatplotlibRenderer,
    "x3d": X3DRenderer,
    "csv": CSVRenderer,
}

_DEPTH_PROVIDER_REGISTRY: dict[str, type[DepthProvider]] = {
    "palette": PaletteDepthProvider,
    "direct": DirectDepthProvider,
}


def create_renderer(name: str, output_folder: str) -> BaseRenderer:
    cls = _RENDERER_REGISTRY.get(name)
    if cls is None:
        available = list(_RENDERER_REGISTRY)
        raise ValueError(f"Renderer '{name}' unknown. Available: {available}")
    return cls(output_folder)


def create_depth_provider(name: str) -> DepthProvider:
    cls = _DEPTH_PROVIDER_REGISTRY.get(name)
    if cls is None:
        available = list(_DEPTH_PROVIDER_REGISTRY)
        raise ValueError(f"DepthProvider '{name}' unknown. Available: {available}")
    return cls()
