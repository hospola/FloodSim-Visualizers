// Compile-time configuration — does not vary between simulation runs.
// Runtime values (grid dimensions, palette, frame list) live in runtime.js.

/** Side length in metres of each chunk in the LOD grid. */
export const CHUNK_M = 1000.0;

/** x_ite LOD `range` attribute — distance breakpoints in metres. */
export const LOD_RANGES = "3000,10000,30000";

/** Mesh cell sizes in metres for each LOD level (matches LOD_RANGES order). */
export const LOD_SIZES = [25.0, 100.0, 500.0];

/** Visual lift in metres added on top of the terrain to draw flooded cells.
 *  Index = palette state (0=dry … 5=extreme). */
export const WATER_LIFT = [0.0, 0.1, 0.4, 1.0, 2.5, 5.0];

/** Human-readable names for the 6 palette states. */
export const STATE_NAMES = [
  "Seco",
  "Muy somero",
  "Profundidad baja",
  "Profundidad media",
  "Profundidad alta",
  "Profundidad extrema",
];
