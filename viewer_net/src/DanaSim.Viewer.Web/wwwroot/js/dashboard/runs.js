import { loadRun, resumeLive } from './viewer.js';

const CFG = window.__DASHBOARD__;

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString();
}

function render(runs) {
  const list = document.getElementById('runsList');
  if (!list) return;

  if (!runs.length) {
    list.innerHTML = '<p class="error-msg">No past runs found.</p>';
    return;
  }

  list.innerHTML = '';
  for (const run of runs) {
    const item = document.createElement('button');
    item.className = 'run-item';
    item.type = 'button';

    const name = document.createElement('span');
    name.className = 'run-name';
    name.textContent = run.name;

    const meta = document.createElement('span');
    meta.className = 'run-meta';
    const frames = run.frameCount != null ? `${run.frameCount} frame(s)` : '';
    const live = run.live ? ' · live' : '';
    meta.textContent = `${frames}${live} · ${formatTime(run.lastModified)}`;

    item.append(name, meta);
    item.addEventListener('click', () => loadRun(run.playerUrl));
    list.appendChild(item);
  }
}

async function loadRuns() {
  try {
    const runs = await fetch(CFG.runsUrl).then(r => r.json());
    render(runs);
  } catch { /* server may be starting */ }
}

export function initRuns() {
  document.getElementById('runsRefreshBtn')?.addEventListener('click', loadRuns);
  document.getElementById('runsLiveBtn')?.addEventListener('click', resumeLive);
  document.addEventListener('panelOpened', e => {
    if (e.detail === 'runs') loadRuns();
  });
  loadRuns();
}
