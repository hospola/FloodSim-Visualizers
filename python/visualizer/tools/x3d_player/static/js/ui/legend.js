// Colour legend — renders the 5 flood depth states with their names and
// palette colours into the #legend container.

import { STATE_NAMES } from "../config.js";
import { STATE_COLORS } from "../runtime.js";

/** Convert an X3D "r g b" float string into a CSS `rgb(R, G, B)` string. */
function _toCss(x3dColor) {
  const [r, g, b] = x3dColor.split(/\s+/).map(v => Math.round(parseFloat(v) * 255));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Build and inject the legend rows into #legend.
 * States 1-5 are shown (index 0 = Dry is intentionally omitted since
 * dry cells are not written to the flood layer).
 *
 * Must be called once after the DOM is ready (does not require the 3D
 * scene to be built — safe to call early).
 */
export function initLegend() {
  const container = document.getElementById("legend");
  if (!container) return;

  const rows = STATE_NAMES.slice(1).map((name, i) => {
    const idx = i + 1;
    const css = STATE_COLORS[idx] ? _toCss(STATE_COLORS[idx]) : "#888";
    return `<div class="legend-row">
      <span class="legend-swatch" style="background:${css}"></span>
      <span class="legend-name">${name}</span>
    </div>`;
  });

  container.innerHTML = rows.join("");
}
