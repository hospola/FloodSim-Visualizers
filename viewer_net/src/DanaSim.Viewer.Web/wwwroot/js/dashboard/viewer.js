let currentSrc = null;
let _manualOverride = false;

function _setSrc(playerUrl) {
  if (playerUrl === currentSrc) return;
  currentSrc = playerUrl;
  const iframe = document.getElementById('viewerFrame');
  if (iframe) iframe.src = playerUrl;
}

export function initViewer() {
  // nothing to set up — iframe starts with about:blank
}

/**
 * Called by the live-status poll with the currently active player URL.
 * Ignored while the user is viewing a past run via `updateViewer(url, true)`.
 */
export function updateViewer(playerUrl) {
  if (_manualOverride) return;
  if (!playerUrl) return;
  _setSrc(playerUrl);
}

/**
 * Load a specific player URL, e.g. from the "Past Runs" list. Suspends
 * automatic follow-the-live-run updates until `resumeLive()` is called.
 * @param {string} playerUrl
 */
export function loadRun(playerUrl) {
  _manualOverride = true;
  currentSrc = null; // force reload even if it's the same URL as before
  _setSrc(playerUrl);
}

/** Resume following the live simulation's player URL. */
export function resumeLive() {
  _manualOverride = false;
  currentSrc = null;
}

export function isManualOverride() {
  return _manualOverride;
}
