// Camera controls — viewpoint presets, vertical exaggeration slider and
// keyboard shortcuts for camera navigation.
//
// Viewpoint binding uses x_ite's `set_bind` inputOnly SFBool field.
// Must be set as a JS property (vp.set_bind = true), NOT via setAttribute —
// x_ite ignores setAttribute for inputOnly fields.
// The ZScale Transform (DEF="ZScale") wraps the entire terrain so we can
// scale Y without touching any geometry data.

/**
 * Bind to a named Viewpoint node embedded in the scene.
 * Exported so other modules (e.g. minimap.js) can trigger camera transitions.
 * @param {string} def  Viewpoint DEF attribute — e.g. "VP_Overview"
 */
export function bindViewpoint(def) {
  // Use x_ite's SAI — getNamedNode returns a scene-graph proxy whose field
  // setters are wired to the x_ite event system. The raw DOM element obtained
  // via querySelector does NOT have those setters (set_bind stays undefined).
  const canvas = document.querySelector("x3d-canvas");
  const vp = canvas?.browser?.currentScene?.getNamedNode(def);
  if (vp) vp.set_bind = true;
}

/**
 * Apply a vertical exaggeration factor to the ZScale Transform.
 * @param {number} factor  1 = real scale, 10 = 10× taller
 */
function _applyZScale(factor) {
  const t = document.querySelector('Transform[DEF="ZScale"]');
  if (t) t.setAttribute("scale", `1 ${factor} 1`);
  const label = document.getElementById("zScaleVal");
  if (label) label.textContent = `${factor}×`;
}

/**
 * Wire up preset buttons, Z-scale slider and keyboard shortcuts.
 * Must be called once after the scene is ready.
 */
export function initCamera() {
  // Preset buttons — each carries data-vp with the target Viewpoint DEF.
  document.querySelectorAll(".cam-btn[data-vp]").forEach(btn => {
    btn.addEventListener("click", () => bindViewpoint(btn.dataset.vp));
  });

  // Reset button — back to the Overview viewpoint.
  const resetBtn = document.getElementById("camReset");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => bindViewpoint("VP_Overview"));
  }

  // Z-scale slider.
  const zSlider = document.getElementById("zScale");
  if (zSlider) {
    zSlider.addEventListener("input", () => _applyZScale(parseFloat(zSlider.value)));
  }

  // Keyboard shortcuts (camera only — playback keys live in playback.js).
  document.addEventListener("keydown", e => {
    // Ignore shortcuts when user is typing inside an input/textarea.
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    switch (e.key.toLowerCase()) {
      case "c": bindViewpoint("VP_Cenital");  break;
      case "p": bindViewpoint("VP_Overview"); break;
      case "l": bindViewpoint("VP_Lateral");  break;
      case "r": bindViewpoint("VP_Overview"); break;
    }
  });
}
