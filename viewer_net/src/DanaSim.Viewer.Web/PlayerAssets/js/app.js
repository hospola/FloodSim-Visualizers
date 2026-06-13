// DanaSim X3D heightmap player — entry point.
//
// Orchestrates the boot sequence: decode the embedded terrain heightmap,
// fetch the first flood frame, build the 3D scene and finally wire up the
// playback controls. Each step updates the loading indicator so the user
// sees progress; any failure is surfaced in the same element.

import { FLOOD_FRAMES } from "./runtime.js";
import { loadTerrain } from "./scene/terrain.js";
import { fetchFloodPx } from "./scene/flood.js";
import { buildScene } from "./scene/scene.js";
import { state } from "./state.js";
import { initCamera } from "./ui/camera.js";
import { initLayers } from "./ui/layers.js";
import { initLegend } from "./ui/legend.js";
import { initMinimap } from "./ui/minimap.js";
import { initPlayback } from "./ui/playback.js";
import { startLivePolling } from "./live.js";

const $loading = document.getElementById("loading");
const $status  = document.getElementById("status");

function setLoading(msg) {
  $loading.textContent = msg;
}

/** Read the current layer toggles (without `floodPx`, scene fills it in). */
function initialLayerOpts() {
  return {
    showTerrain: state.layers.terrain,
    showWater:   state.layers.water,
    stateMask:   state.layers.states,
  };
}

(async () => {
  const tBoot0 = performance.now();
  try {
    setLoading("Step 1/3: Decoding terrain PNG…");
    const t1 = performance.now();
    await loadTerrain();
    const terrainMs = performance.now() - t1;

    setLoading("Step 2/3: Fetching flood data…");
    const t2 = performance.now();
    const initFlood = FLOOD_FRAMES.length > 0
      ? await fetchFloodPx(FLOOD_FRAMES[0])
      : null;
    const floodMs = performance.now() - t2;

    setLoading("Step 3/3: Building 3D scene…");
    const t3 = performance.now();
    await buildScene(initFlood, initialLayerOpts(), setLoading);
    const sceneMs = performance.now() - t3;

    $loading.style.display = "none";

    initPlayback();
    initLayers();
    initCamera();
    initLegend();
    initMinimap();
    startLivePolling();

    console.log(
      `[PERF] boot sequence: total=${(performance.now() - tBoot0).toFixed(0)}ms ` +
      `(terrain=${terrainMs.toFixed(0)}ms, firstFlood=${floodMs.toFixed(0)}ms, ` +
      `buildScene=${sceneMs.toFixed(0)}ms)`);
  } catch (err) {
    setLoading("Error: " + err.message);
    console.error("Scene init failed:", err);
  }
})();
