export function initStatus() {
  // initial DOM state already set by HTML defaults
}

export function updateStatus(s) {
  setDot(s.connectionStatus, s.phase, s.lastError);
  setText('statusText',   s.connectionStatus);
  setText('phase',        s.phase        || 'Idle');
  setText('frameCount',   s.frameCount   ?? 0);
  setText('simTime',      s.simulationTime || '—');
  setText('scenarioText', s.scenario     || '—');

  const errEl = document.getElementById('lastError');
  if (errEl) errEl.textContent = s.lastError ?? '';
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setDot(connectionStatus, phase, lastError) {
  const dot = document.getElementById('statusDot');
  if (!dot) return;

  dot.className = 'dot';

  if (lastError && connectionStatus !== 'Connected') {
    dot.classList.add('red');
  } else if (connectionStatus === 'Connected' && phase === 'Running') {
    dot.classList.add('green');
  } else if (connectionStatus === 'Connecting' || phase === 'Initialising') {
    dot.classList.add('yellow');
  } else if (connectionStatus === 'Disconnected') {
    dot.classList.add('red');
  }
  // grey = Idle / Ended / default (no extra class)
}
