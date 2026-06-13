"""X3D heightmap player generator — modular replacement for generate_x3d_heightmap.

Phase 1: refactor only — splits the previous monolithic f-string into:
  - template.html.j2  (Jinja2 HTML skeleton)
  - static/css/style.css
  - static/js/app.js
  - generator.py      (Python entry point — data prep + asset inlining)

Output is functionally identical to the old generator: a self-contained
player.html plus a flood/ directory with frame PNGs.
"""
from .generator import main, generate_player

__all__ = ["main", "generate_player"]
