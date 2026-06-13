"""Backward-compatible shim — delegates to the new ``x3d_player`` package.

The legacy module path ``python.visualizer.tools.generate_x3d_heightmap`` and
its ``main`` entry point still work; everything is implemented in
``x3d_player.generator``.

Run as::

    python -m python.visualizer.tools.generate_x3d_heightmap \\
        --csv outputs/csv_data/ \\
        --output outputs/x3d_heightmap/

(or use the new path ``python -m python.visualizer.tools.x3d_player`` — both
produce identical output).
"""
from __future__ import annotations

import sys

from .x3d_player.generator import generate_player, main

__all__ = ["main", "generate_player"]


if __name__ == "__main__":
    sys.exit(main())
