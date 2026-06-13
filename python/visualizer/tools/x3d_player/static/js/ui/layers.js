// Layer toggle controls — wires the sidebar checkboxes to `state.layers` and
// pushes the resulting opts through to `scene.setLayers` for instant feedback.
//
// Sidebar markup expected in the page:
//   #layerTerrain                     (master "show terrain" checkbox)
//   #layerWater                       (master "show water" checkbox)
//   #layerState1 … #layerState5       (one per palette state, dry omitted)

import { STATE_NAMES } from "../config.js";
import { STATE_COLORS } from "../runtime.js";
import { setLayers } from "../scene/scene.js";
import { state, update } from "../state.js";

/** Convert an X3D "r g b" float string into a CSS `rgb(R,G,B)` string. */
function _x3dColorToCss(x3dColor) {
  const [r, g, b] = x3dColor.split(/\s+/).map(v => Math.round(parseFloat(v) * 255));
  return `rgb(${r}, ${g}, ${b})`;
}

function _paintSwatches() {
  document.querySelectorAll(".swatch[data-state]").forEach(el => {
    const idx = parseInt(el.getAttribute("data-state"), 10);
    if (Number.isFinite(idx) && STATE_COLORS[idx]) {
      el.style.backgroundColor = _x3dColorToCss(STATE_COLORS[idx]);
    }
  });
}

/** @returns {import("../scene/builder.js").BuildOpts} */
function _toBuildOpts(layers) {
  return {
    floodPx: null,                    // injected by scene.js from its cache
    showTerrain: layers.terrain,
    showWater:   layers.water,
    stateMask:   layers.states,
  };
}

function _onTerrainChange(e) {
  const layers = { ...state.layers, terrain: e.target.checked };
  update({ layers });
  setLayers(_toBuildOpts(layers));
}

function _onWaterChange(e) {
  const layers = { ...state.layers, water: e.target.checked };
  update({ layers });
  // When water is off, sub-state checkboxes are visually disabled but their
  // values are still stored — re-enabling water restores them.
  _refreshStateCheckboxes(layers);
  setLayers(_toBuildOpts(layers));
}

function _onStateChange(idx, e) {
  const states = state.layers.states.slice();
  states[idx] = e.target.checked;
  const layers = { ...state.layers, states };
  update({ layers });
  setLayers(_toBuildOpts(layers));
}

function _refreshStateCheckboxes(layers) {
  for (let i = 1; i < layers.states.length; i++) {
    const cb = document.getElementById(`layerState${i}`);
    if (!cb) continue;
    cb.disabled = !layers.water;
  }
}

/** Attach an `aria-label` mirroring the visible name for the screen reader. */
function _labelStateCheckbox(idx) {
  const cb = document.getElementById(`layerState${idx}`);
  if (cb) cb.setAttribute("aria-label", STATE_NAMES[idx] ?? `state ${idx}`);
}

/**
 * Wire up event listeners and seed the DOM from the current state.
 * Must be called once after the scene is built.
 */
export function initLayers() {
  const terrain = document.getElementById("layerTerrain");
  const water = document.getElementById("layerWater");
  if (!terrain || !water) return;  // template did not include the sidebar

  terrain.checked = state.layers.terrain;
  water.checked = state.layers.water;
  terrain.addEventListener("change", _onTerrainChange);
  water.addEventListener("change", _onWaterChange);

  for (let i = 1; i < state.layers.states.length; i++) {
    const cb = document.getElementById(`layerState${i}`);
    if (!cb) continue;
    cb.checked = state.layers.states[i];
    cb.addEventListener("change", e => _onStateChange(i, e));
    _labelStateCheckbox(i);
  }
  _refreshStateCheckboxes(state.layers);
  _paintSwatches();

  // Sidebar collapse toggle.
  const toggle = document.getElementById("sidebarToggle");
  const sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("collapsed"));
  }
}
