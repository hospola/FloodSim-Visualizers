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
  const t0 = performance.now();
  try {
    const tFetch0 = performance.now();
    const resp = await fetch(`flood/${frameName}.png`);
    if (!resp.ok) return null;
    const blob = await resp.blob();
    const fetchMs = performance.now() - tFetch0;

    const tDecode0 = performance.now();
    const bitmap = await createImageBitmap(blob);
    const decodeMs = performance.now() - tDecode0;

    if (!_floodCanvas) {
      _floodCanvas = document.createElement("canvas");
      _floodCanvas.width = PNG_COLS;
      _floodCanvas.height = PNG_ROWS;
      _floodCtx = _floodCanvas.getContext("2d");
    }
    const tDraw0 = performance.now();
    _floodCtx.drawImage(bitmap, 0, 0);
    const px = _floodCtx.getImageData(0, 0, PNG_COLS, PNG_ROWS).data;
    const drawMs = performance.now() - tDraw0;

    console.log(
      `[PERF] fetchFloodPx ${frameName}: total=${(performance.now() - t0).toFixed(0)}ms ` +
      `(fetch=${fetchMs.toFixed(0)}ms [${(blob.size / 1024).toFixed(1)} KB], ` +
      `decode=${decodeMs.toFixed(0)}ms, draw=${drawMs.toFixed(0)}ms)`);

    return px;
  } catch (e) {
    return null;
  }
}
