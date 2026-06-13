// Playback controls — wires the slider, prev/next/play buttons and the
// speed slider to the state container and the scene update pipeline.
//
// Uses state.js for `frame` and `playing`; the DOM is the source of truth
// for `speed` since it's read-only from JS's perspective.

import { FLOOD_FRAMES } from "../runtime.js";
import { fetchFloodPx } from "../scene/flood.js";
import { setFrame as sceneSetFrame } from "../scene/scene.js";
import { state, update } from "../state.js";

let _timer = null;

function _frameLabel(i) {
  return `Frame ${i} / ${FLOOD_FRAMES.length - 1}`;
}

/** @returns {import("../scene/builder.js").BuildOpts} */
function _layerOpts() {
  return {
    floodPx: null,
    showTerrain: state.layers.terrain,
    showWater:   state.layers.water,
    stateMask:   state.layers.states,
  };
}

/**
 * Show frame `i` (modulo the frame list). If it differs from the currently
 * displayed frame, fetch the flood PNG and push it to the scene with the
 * current layer opts.
 * @param {number} i
 */
async function setFrame(i) {
  const n = FLOOD_FRAMES.length;
  const next = ((i % n) + n) % n;
  document.getElementById("slider").value = next;
  document.getElementById("frame-label").textContent = _frameLabel(next);

  if (next === state.frame) return;
  update({ frame: next });

  const floodPx = await fetchFloodPx(FLOOD_FRAMES[next]);
  sceneSetFrame(floodPx, _layerOpts());
}

function startPlay() {
  const ms = parseInt(document.getElementById("speed").value);
  _timer = setInterval(() => setFrame(state.frame + 1), ms);
  update({ playing: true });
  document.getElementById("playBtn").textContent = "⏸ Pause";
}

function stopPlay() {
  clearInterval(_timer);
  _timer = null;
  update({ playing: false });
  document.getElementById("playBtn").textContent = "▶ Play";
}

/**
 * Jump to the last available frame. Used by live polling when auto-follow is on.
 */
export function goToLatest() {
  setFrame(FLOOD_FRAMES.length - 1);
}

/**
 * Wire up event listeners and keyboard shortcuts.
 * Must be called once after the scene is ready.
 */
export function initPlayback() {
  document.getElementById("playBtn").addEventListener("click",
    () => state.playing ? stopPlay() : startPlay());

  document.getElementById("prevBtn").addEventListener("click",
    () => { stopPlay(); setFrame(state.frame - 1); });

  document.getElementById("nextBtn").addEventListener("click",
    () => { stopPlay(); setFrame(state.frame + 1); });

  document.getElementById("slider").addEventListener("input",
    e => { stopPlay(); setFrame(parseInt(e.target.value)); });

  document.getElementById("speed").addEventListener("change",
    () => { if (state.playing) { stopPlay(); startPlay(); } });

  // Keyboard shortcuts for playback.
  document.addEventListener("keydown", e => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    switch (e.key) {
      case " ":
        e.preventDefault();  // prevent page scroll
        state.playing ? stopPlay() : startPlay();
        break;
      case "ArrowLeft":
        stopPlay(); setFrame(state.frame - 1);
        break;
      case "ArrowRight":
        stopPlay(); setFrame(state.frame + 1);
        break;
    }
  });
}
