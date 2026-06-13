// Runtime configuration — values injected by the Python generator into
// `window.__CONFIG__` before the module graph loads. Re-exported as named
// constants so the rest of the JS code can `import` them like any other module.

const CFG = window.__CONFIG__;

if (!CFG) {
  throw new Error("window.__CONFIG__ is not defined — generator did not inject it.");
}

/** Width of the terrain PNG in pixels. */
export const PNG_COLS = CFG.pngCols;

/** Height of the terrain PNG in pixels. */
export const PNG_ROWS = CFG.pngRows;

/** Metres per terrain PNG pixel (sampling resolution). */
export const PNG_RES = CFG.pngRes;

/** Domain width in metres (cols × cell_size). */
export const MAP_W = CFG.mapW;

/** Domain depth in metres (rows × cell_size). */
export const MAP_D = CFG.mapD;

/** Minimum terrain elevation in metres (used to decode PNG pixels). */
export const MIN_H = CFG.minH;

/** Maximum terrain elevation in metres (used to decode PNG pixels). */
export const MAX_H = CFG.maxH;

/** Six "r g b" floating-point colour strings, indexed by palette state. */
export const STATE_COLORS = CFG.stateColors;

/** Names of the flood frame PNG files (relative to `flood/`, no extension). */
export const FLOOD_FRAMES = CFG.floodFrames;

/** Data URL or path for the terrain heightmap image. */
export const TERRAIN_SRC = CFG.terrainSrc;
