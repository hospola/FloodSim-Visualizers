// Live updates via SignalR push, with manifest-polling fallback.
// startLivePolling() is called once after the scene is ready.

import { FLOOD_FRAMES } from "./runtime.js";
import { goToLatest }   from "./ui/playback.js";

const CFG = window.__CONFIG__;

let _autoFollow = false;

function _updateSlider() {
  const slider = document.getElementById("slider");
  if (slider) slider.max = Math.max(0, FLOOD_FRAMES.length - 1);
}

function _setLiveStatus(live, count) {
  const el = document.getElementById("status");
  if (!el) return;
  if (live) {
    el.textContent = `🔴 En vivo — ${count} frame(s)`;
    el.style.color = "#e44";
  } else {
    el.textContent = `✅ Completado — ${count} frame(s)`;
    el.style.color = "";
  }
}

function _setFollowActive(active) {
  _autoFollow = active;
  const btn = document.getElementById("followBtn");
  if (!btn) return;
  btn.textContent      = active ? "📍 Siguiendo" : "📍 Seguir";
  btn.style.background = active ? "#e44" : "";
  btn.style.color      = active ? "#fff" : "";
}

function _syncFrames(frames) {
  const known = new Set(FLOOD_FRAMES);
  let added = 0;
  for (const name of frames) {
    if (!known.has(name)) { FLOOD_FRAMES.push(name); added++; }
  }
  if (added > 0) {
    _updateSlider();
    if (_autoFollow) goToLatest();
  }
}

async function _fetchManifest() {
  try {
    const res = await fetch(`flood/manifest.json?t=${Date.now()}`);
    return res.ok ? res.json() : null;
  } catch { return null; }
}

function _startPollingFallback() {
  _setLiveStatus(true, FLOOD_FRAMES.length);
  _updateSlider();
  const timer = setInterval(async () => {
    const manifest = await _fetchManifest();
    if (!manifest) return;
    _syncFrames(manifest.frames);
    _setLiveStatus(manifest.live, FLOOD_FRAMES.length);
    if (!manifest.live) {
      clearInterval(timer);
      _setFollowActive(false);
      const btn = document.getElementById("followBtn");
      if (btn) btn.disabled = true;
    }
  }, 2000);
}

export async function startLivePolling() {
  const followBtn = document.getElementById("followBtn");
  if (followBtn) followBtn.addEventListener("click", () => _setFollowActive(!_autoFollow));

  // Single manifest fetch — if live=false this is a finished/historical run
  const manifest = await _fetchManifest();
  if (!manifest?.live) {
    _syncFrames(manifest?.frames ?? []);
    _setLiveStatus(false, FLOOD_FRAMES.length);
    if (followBtn) followBtn.disabled = true;
    return;
  }

  // Attempt SignalR connection
  const scenario = CFG.scenario;
  if (!scenario || !window.signalR) {
    _startPollingFallback();
    return;
  }

  const connection = new window.signalR.HubConnectionBuilder()
    .withUrl("/simulationHub")
    .withAutomaticReconnect()
    .build();

  connection.on("FrameReady", stepName => {
    if (!FLOOD_FRAMES.includes(stepName)) {
      FLOOD_FRAMES.push(stepName);
      _updateSlider();
      if (_autoFollow) goToLatest();
    }
    _setLiveStatus(true, FLOOD_FRAMES.length);
  });

  connection.on("SimulationEnded", () => {
    _setLiveStatus(false, FLOOD_FRAMES.length);
    _setFollowActive(false);
    if (followBtn) followBtn.disabled = true;
    connection.stop();
  });

  try {
    await connection.start();
    await connection.invoke("JoinScenario", scenario);
    _setLiveStatus(true, FLOOD_FRAMES.length);
    _updateSlider();
  } catch (err) {
    console.warn("SignalR unavailable, falling back to manifest polling:", err);
    connection.stop().catch(() => {});
    _startPollingFallback();
  }
}
