from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

RGB = tuple[float, float, float]

_DEFAULT_STATE_COLORS: list[RGB] = [
    (0.62, 0.50, 0.25),   # 0: Dry
    (0.60, 0.90, 1.00),   # 1: Very Shallow
    (0.20, 0.60, 0.90),   # 2: Low Depth
    (0.10, 0.40, 0.80),   # 3: Medium Depth
    (0.05, 0.20, 0.70),   # 4: High Depth
    (0.10, 0.10, 0.60),   # 5: Extreme Depth
]


@dataclass
class X3DColorScheme:
    """Colors for X3D rendering. state_colors maps palette index (0-5) to RGB."""
    sky: RGB = (0.53, 0.81, 0.98)
    state_colors: list[RGB] = field(default_factory=lambda: list(_DEFAULT_STATE_COLORS))

    def state_rgb(self, state: int) -> RGB:
        idx = max(0, min(state, len(self.state_colors) - 1))
        return self.state_colors[idx]

    def palette_color_str(self) -> str:
        """Flat X3D Color string with one RGB per state (used by Color node)."""
        return "  ".join(f"{r:.2f} {g:.2f} {b:.2f}" for r, g, b in self.state_colors)


def load_colors(palette_path: Path) -> X3DColorScheme:
    """Load X3D colors from color_palette.json.

    Reads state_colors from the optional 'x3d' section first.
    Falls back to 'layers.flood_risk[].rgba' (0-255) if present.
    Uses hardcoded defaults if neither is found.
    """
    try:
        data = json.loads(palette_path.read_text(encoding="utf-8"))

        x3d = data.get("x3d", {})
        if x3d:
            sky: RGB = tuple(x3d.get("sky_rgb", (0.53, 0.81, 0.98)))  # type: ignore[assignment]
            raw_states = x3d.get("state_colors", [])
            state_colors: list[RGB] = [tuple(c) for c in raw_states] if raw_states else list(_DEFAULT_STATE_COLORS)  # type: ignore[misc]
            return X3DColorScheme(sky=sky, state_colors=state_colors)

        flood_risk = data.get("layers", {}).get("flood_risk", [])
        if flood_risk:
            sorted_levels = sorted(flood_risk, key=lambda e: e["value"])
            state_colors = [
                (e["rgba"][0] / 255.0, e["rgba"][1] / 255.0, e["rgba"][2] / 255.0)
                for e in sorted_levels
            ]
            return X3DColorScheme(state_colors=state_colors)

        return X3DColorScheme()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Could not load X3D colors from %s: %s. Using defaults.", palette_path, exc
        )
        return X3DColorScheme()
