const CFG = window.__DASHBOARD__;

function clearErrors() {
  document.querySelectorAll('.field-error').forEach(el => el.textContent = '');
}

function showErrors(errors) {
  clearErrors();
  for (const [field, msg] of Object.entries(errors)) {
    const el = document.getElementById(`err-${field}`);
    if (el) el.textContent = msg;
  }
}

function readForm() {
  return {
    mqttHost:       document.getElementById('cfg-host').value.trim(),
    mqttPort:       parseInt(document.getElementById('cfg-port').value, 10) || 0,
    scenario:       document.getElementById('cfg-scenario').value.trim(),
    terrainBasePath: document.getElementById('cfg-terrain').value.trim(),
    outputDir:      document.getElementById('cfg-output').value.trim(),
  };
}

function populateForm(cfg) {
  document.getElementById('cfg-host').value     = cfg.mqttHost     ?? '';
  document.getElementById('cfg-port').value     = cfg.mqttPort     ?? 1883;
  document.getElementById('cfg-scenario').value = cfg.scenario     ?? '';
  document.getElementById('cfg-terrain').value  = cfg.terrainBasePath ?? '';
  document.getElementById('cfg-output').value   = cfg.outputDir    ?? '';
}

function setFeedback(msg, isError = false) {
  const el = document.getElementById('saveFeedback');
  if (!el) return;
  el.textContent  = msg;
  el.style.color  = isError ? '#f44' : '#4c4';
  if (msg) setTimeout(() => { el.textContent = ''; }, 3000);
}

export async function initConfig() {
  try {
    const cfg = await fetch(CFG.configUrl).then(r => r.json());
    populateForm(cfg);
  } catch { /* ignore on startup */ }

  document.getElementById('saveBtn')?.addEventListener('click', async () => {
    clearErrors();
    const res = await fetch(CFG.configUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(readForm()),
    });
    if (res.ok) {
      setFeedback('Saved — reconnecting…');
    } else {
      const body = await res.json().catch(() => ({}));
      if (body.errors) showErrors(body.errors);
      else setFeedback(body.error ?? 'Save failed', true);
    }
  });

  document.getElementById('connectBtn')?.addEventListener('click', async () => {
    await fetch(CFG.connectUrl, { method: 'POST' });
  });

  document.getElementById('disconnectBtn')?.addEventListener('click', async () => {
    await fetch(CFG.disconnectUrl, { method: 'POST' });
  });
}
