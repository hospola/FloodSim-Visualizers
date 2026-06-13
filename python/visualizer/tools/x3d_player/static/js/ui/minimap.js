// Minimap — a small 2D overview canvas of the terrain domain.
//
// The terrain heightmap PNG (already embedded in the page) is drawn at canvas
// resolution as the background. The user can click and drag to draw a
// rubber-band selection; on mouse-up the camera flies to that world-space
// bounding box via the VP_Zone Viewpoint node.
//
// Reset restores the VP_Overview camera position.

import { MAP_W, MAP_D, TERRAIN_SRC, MIN_H, MAX_H } from "../runtime.js";
import { bindViewpoint } from "./camera.js";
import { TERRAIN_COLOR_STOPS } from "../scene/terrain.js";

let _canvas = null;
let _ctx = null;
let _terrainImg = null;
let _startPx = null;

async function _loadTerrainImage() {
  return new Promise(resolve => {
    _terrainImg = new Image();
    _terrainImg.onload = resolve;
    _terrainImg.src = TERRAIN_SRC;
  });
}

/**
 * Apply the same terrain colour ramp used by the 3D scene to the canvas.
 * Converts each grayscale pixel back to metres using MIN_H/MAX_H, then
 * looks up the colour from TERRAIN_COLOR_STOPS.
 */
function _applyColormap(ctx, w, h) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  const range = MAX_H - MIN_H;
  for (let i = 0; i < d.length; i += 4) {
    const height = (d[i] / 255) * range + MIN_H;
    let r = 0.51, g = 0.44, b = 0.29;
    for (const [maxH, cr, cg, cb] of TERRAIN_COLOR_STOPS) {
      if (height <= maxH) { r = cr; g = cg; b = cb; break; }
    }
    d[i]     = Math.round(r * 255);
    d[i + 1] = Math.round(g * 255);
    d[i + 2] = Math.round(b * 255);
  }
  ctx.putImageData(img, 0, 0);
}

function _redraw(selRect = null) {
  if (!_ctx) return;
  const w = _canvas.width;
  const h = _canvas.height;
  _ctx.clearRect(0, 0, w, h);

  if (_terrainImg) {
    _ctx.drawImage(_terrainImg, 0, 0, w, h);
    _applyColormap(_ctx, w, h);
  } else {
    _ctx.fillStyle = "#1a2a3a";
    _ctx.fillRect(0, 0, w, h);
  }

  if (selRect) {
    _ctx.fillStyle = "rgba(26, 110, 168, 0.25)";
    _ctx.fillRect(selRect.x, selRect.y, selRect.w, selRect.h);
    _ctx.strokeStyle = "#5ab4f5";
    _ctx.lineWidth = 1.5;
    _ctx.strokeRect(selRect.x, selRect.y, selRect.w, selRect.h);
  }
}

/** Convert canvas pixel coords to world-space (metres). */
function _toWorld(px, py) {
  return {
    x: (px / _canvas.width)  * MAP_W,
    z: (py / _canvas.height) * MAP_D,
  };
}

/**
 * Update VP_Zone and bind to it so the camera flies to the selected area.
 * @param {number} x0  world X start
 * @param {number} z0  world Z start
 * @param {number} x1  world X end
 * @param {number} z1  world Z end
 */
function _flyToArea(x0, z0, x1, z1) {
  const cx   = (x0 + x1) / 2;
  const cz   = (z0 + z1) / 2;
  const span = Math.max(Math.abs(x1 - x0), Math.abs(z1 - z0));
  const camH = Math.max(span * 1.1, 500);

  const vp = document.querySelector('Viewpoint[DEF="VP_Zone"]');
  if (vp) {
    vp.setAttribute("position",    `${cx.toFixed(0)} ${camH.toFixed(0)} ${cz.toFixed(0)}`);
    vp.setAttribute("orientation", "1 0 0 -1.5708");
    bindViewpoint("VP_Zone");
  }
}

/** Canvas-relative pixel coords from a mouse event. */
function _px(e) {
  const r = _canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

/**
 * Initialise the minimap canvas. Should be called once after the scene is ready.
 * Loads the terrain preview asynchronously — the canvas shows a placeholder
 * until the image is available.
 */
export async function initMinimap() {
  _canvas = document.getElementById("minimapCanvas");
  if (!_canvas) return;

  _ctx = _canvas.getContext("2d");

  // Set pixel dimensions to match the domain aspect ratio.
  const cssW = _canvas.offsetWidth || 240;
  _canvas.width  = cssW;
  _canvas.height = Math.round(cssW * (MAP_D / MAP_W));

  _redraw();  // placeholder until terrain loads

  _loadTerrainImage().then(() => _redraw());

  // Reset button — go back to full-domain Overview.
  const resetBtn = document.getElementById("minimapReset");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      _redraw();
      bindViewpoint("VP_Overview");
    });
  }

  // Rubber-band selection.
  _canvas.addEventListener("mousedown", e => {
    _startPx = _px(e);
  });

  _canvas.addEventListener("mousemove", e => {
    if (!_startPx) return;
    const cur = _px(e);
    _redraw({
      x: Math.min(_startPx.x, cur.x),
      y: Math.min(_startPx.y, cur.y),
      w: Math.abs(cur.x - _startPx.x),
      h: Math.abs(cur.y - _startPx.y),
    });
  });

  _canvas.addEventListener("mouseup", e => {
    if (!_startPx) return;
    const endPx = _px(e);
    const dx = Math.abs(endPx.x - _startPx.x);
    const dy = Math.abs(endPx.y - _startPx.y);

    if (dx > 5 || dy > 5) {
      const w0 = _toWorld(_startPx.x, _startPx.y);
      const w1 = _toWorld(endPx.x, endPx.y);
      _flyToArea(w0.x, w0.z, w1.x, w1.z);
    }

    _startPx = null;
    _redraw();
  });

  _canvas.addEventListener("mouseleave", () => {
    if (_startPx) { _startPx = null; _redraw(); }
  });
}
