"""Centralized flood-risk color palette.

A single canonical representation, resolved once per run from (in order of
preference):
  1. the `color_palette` field of an InitAgent_Layer MQTT message
  2. the `layers.flood_risk` section of a color_palette.json file on disk
  3. hardcoded defaults

Every renderer (matplotlib snapshots, X3D scenes, the web player config)
derives its own representation from this single object instead of re-parsing
raw palette data.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

RGBA = tuple[int, int, int, int]
RGB_FLOAT = tuple[float, float, float]


@dataclass(frozen=True)
class PaletteEntry:
    value: int
    label: str
    hex: str
    rgba: RGBA


@dataclass(frozen=True)
class Palette:
    """Flood-risk levels sorted by ascending value (index 0 = Dry)."""

    entries: tuple[PaletteEntry, ...]

    @property
    def min_value(self) -> int:
        return self.entries[0].value

    @property
    def max_value(self) -> int:
        return self.entries[-1].value

    def labels(self) -> list[str]:
        return [e.label for e in self.entries]

    def hex_colors(self) -> list[str]:
        """Hex strings ('#RRGGBB[AA]'), e.g. for matplotlib ListedColormap."""
        return [e.hex for e in self.entries]

    def rgb_floats(self) -> list[RGB_FLOAT]:
        """RGB triples in 0.0-1.0 range, e.g. for X3D color nodes."""
        return [(r / 255.0, g / 255.0, b / 255.0) for r, g, b, _ in (e.rgba for e in self.entries)]

    def rgb_strings(self) -> list[str]:
        """'r g b' floating-point strings (0.0-1.0), for the web player config."""
        return [f"{r:.2f} {g:.2f} {b:.2f}" for r, g, b in self.rgb_floats()]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @staticmethod
    def _from_items(items: list[dict]) -> "Palette | None":
        if not isinstance(items, list) or not items:
            return None
        try:
            entries = tuple(
                PaletteEntry(
                    value=int(item["value"]),
                    label=str(item.get("label", "")),
                    hex=str(item["hex"]),
                    rgba=tuple(int(c) for c in item["rgba"]),  # type: ignore[arg-type]
                )
                for item in sorted(items, key=lambda i: int(i["value"]))
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Malformed palette entries (%s) — ignoring", exc)
            return None
        return Palette(entries=entries)

    @staticmethod
    def from_message(color_palette: list[dict] | None) -> "Palette | None":
        """Parse the `color_palette` field of an InitAgent_Layer MQTT message."""
        if color_palette is None:
            return None
        return Palette._from_items(color_palette)

    @staticmethod
    def from_file(path: Path | None) -> "Palette | None":
        """Parse the `layers.flood_risk` section of a color_palette.json file."""
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read palette file %s (%s)", path, exc)
            return None
        return Palette._from_items(data.get("layers", {}).get("flood_risk", []))

    @staticmethod
    def default() -> "Palette":
        defaults = [
            (0, "Dry",            "#9E8050", (158, 128,  80, 255)),
            (1, "Very Shallow",   "#99E6FF", (153, 230, 255, 255)),
            (2, "Low Depth",      "#3399E6", ( 51, 153, 230, 255)),
            (3, "Medium Depth",   "#1A66CC", ( 26, 102, 204, 255)),
            (4, "High Depth",     "#0D33B3", ( 13,  51, 179, 255)),
            (5, "Extreme Depth",  "#1A1A99", ( 26,  26, 153, 255)),
        ]
        return Palette(entries=tuple(PaletteEntry(*d) for d in defaults))


def resolve_palette(message_palette: list[dict] | None, file_path: Path | None) -> Palette:
    """Resolve the palette to use: MQTT message, then file, then defaults."""
    palette = Palette.from_message(message_palette)
    if palette is not None:
        logger.info("Color palette resolved from InitAgent_Layer message (%d levels)", len(palette.entries))
        return palette

    palette = Palette.from_file(file_path)
    if palette is not None:
        logger.info("Color palette resolved from file %s (%d levels)", file_path, len(palette.entries))
        return palette

    logger.info("Color palette not provided by message or file — using defaults")
    return Palette.default()
