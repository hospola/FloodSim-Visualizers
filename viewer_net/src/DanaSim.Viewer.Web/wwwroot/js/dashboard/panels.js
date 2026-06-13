const STORAGE_KEY = 'danasim-panels';

function loadState() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'); }
  catch { return {}; }
}

function saveState(s) { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); }

function updateSidebarVisibility() {
  const allHidden = ['config', 'status'].every(
    n => document.querySelector(`[data-panel="${n}"]`)?.classList.contains('collapsed')
  );
  document.getElementById('dashboard')?.classList.toggle('sidebar-hidden', allHidden);
}

function applyCollapse(name, collapsed) {
  document.querySelector(`[data-panel="${name}"]`)?.classList.toggle('collapsed', collapsed);
  document.querySelector(`[data-toggle="${name}"]`)?.classList.toggle('active', !collapsed);
  updateSidebarVisibility();
}

function toggle(name) {
  const el = document.querySelector(`[data-panel="${name}"]`);
  if (!el) return;
  const nowCollapsed = !el.classList.contains('collapsed');
  applyCollapse(name, nowCollapsed);

  const state = loadState();
  state[name] = !nowCollapsed;
  saveState(state);

  if (!nowCollapsed)
    document.dispatchEvent(new CustomEvent('panelOpened', { detail: name }));
}

export function initPanels() {
  const state = loadState();
  ['config', 'status', 'runs', 'logs'].forEach(name => {
    applyCollapse(name, state[name] === false);
  });

  document.querySelectorAll('[data-toggle]').forEach(btn =>
    btn.addEventListener('click', () => toggle(btn.dataset.toggle))
  );

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    const map = { c: 'config', s: 'status', r: 'runs', l: 'logs' };
    const name = map[e.key.toLowerCase()];
    if (name) { toggle(name); return; }
    if (e.key.toLowerCase() === 'f')
      document.getElementById('dashboard')?.classList.toggle('fullscreen');
  });
}
