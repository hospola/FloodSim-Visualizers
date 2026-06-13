// Flood frame loading — fetches a frame's PNG, decodes it, and returns the
// flat RGBA pixel buffer. The canvas is reused across calls for efficiency.

import { PNG_COLS, PNG_ROWS } from "../runtime.js";

let _floodCanvas = null;
let _floodCtx = null;

/**
 * Fetch and decode the flood PNG for a given frame name.
 * Returns null if the file is missing or the request fails.
 * @param {string} frameName  base name without extension (e.g. "step_00000")
 * @returns {Promise<Uint8ClampedArray | null>}
 */
export async function fetchFloodPx(frameName) {
  try {
    const resp = await fetch(`flood/${frameName}.png`);
    if (!resp.ok) return null;
    const bitmap = await createImageBitmap(await resp.blob());
    if (!_floodCanvas) {
      _floodCanvas = document.createElement("canvas");
      _floodCanvas.width = PNG_COLS;
      _floodCanvas.height = PNG_ROWS;
      _floodCtx = _floodCanvas.getContext("2d");
    }
    _floodCtx.drawImage(bitmap, 0, 0);
    return _floodCtx.getImageData(0, 0, PNG_COLS, PNG_ROWS).data;
  } catch (e) {
    return null;
  }
}
