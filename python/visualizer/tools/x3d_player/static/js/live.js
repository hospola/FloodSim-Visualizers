// Live simulation polling — checks flood/manifest.json for new frames
// and extends FLOOD_FRAMES so playback.js picks them up automatically.
//
// Call startLivePolling() once after the scene is ready.
// Polling stops automatically when the manifest reports live=false.

import { FLOOD_FRAMES } from "./runtime.js";
import { goToLatest } from "./ui/playback.js";

const POLL_INTERVAL_MS = 2000;

let _timer      = null;
let _autoFollow = false;

function _updateSlider() {
  const n = FLOOD_FRAMES.length;
  const slider = document.getElementById("slider");
  if (slider) slider.max = Math.max(0, n - 1);
}

function _setLiveStatus(live, frameCount) {
  const el = document.getElementById("status");
  if (!el) return;
  if (live) {
    el.textContent = `🔴 En vivo — ${frameCount} frame(s)`;
    el.style.color = "#e44";
  } else {
    el.textContent = `✅ Completado — ${frameCount} frame(s)`;
    el.style.color = "";
  }
}

function _setFollowActive(active) {
  _autoFollow = active;
  const btn = document.getElementById("followBtn");
  if (!btn) return;
  btn.textContent = active ? "📍 Siguiendo" : "📍 Seguir";
  btn.style.background = active ? "#e44" : "";
  btn.style.color      = active ? "#fff" : "";
}

async function _poll() {
  let manifest;
  try {
    const res = await fetch(`flood/manifest.json?t=${Date.now()}`);
    if (!res.ok) return;
    manifest = await res.json();
  } catch {
    return;
  }

  const known = new Set(FLOOD_FRAMES);
  let added = 0;
  for (const name of manifest.frames) {
    if (!known.has(name)) {
      FLOOD_FRAMES.push(name);
      added++;
    }
  }

  if (added > 0) {
    _updateSlider();
    if (_autoFollow) goToLatest();
  }

  _setLiveStatus(manifest.live, FLOOD_FRAMES.length);

  if (!manifest.live) {
    clearInterval(_timer);
    _timer = null;
    _setFollowActive(false);
    const btn = document.getElementById("followBtn");
    if (btn) btn.disabled = true;
  }
}

/**
 * Start polling flood/manifest.json for new frames.
 * Safe to call even if the manifest doesn't exist yet.
 */
export function startLivePolling() {
  const btn = document.getElementById("followBtn");
  if (btn) {
    btn.addEventListener("click", () => _setFollowActive(!_autoFollow));
  }

  _setLiveStatus(true, FLOOD_FRAMES.length);
  _updateSlider();
  _timer = setInterval(_poll, POLL_INTERVAL_MS);
  _poll();
}
