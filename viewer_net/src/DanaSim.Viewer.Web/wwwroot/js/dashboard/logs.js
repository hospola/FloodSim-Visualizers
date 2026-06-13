const MAX_ENTRIES = 500;
const COLOURS = { DBG: '#666', INF: '#4af', WRN: '#fa0', ERR: '#f44', FTL: '#f44' };

let unseenErrors = 0;
const activeFilters = new Set(['DBG', 'INF', 'WRN', 'ERR', 'FTL']);

function isAtBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 4;
}

function enforceMax(list) {
  while (list.childElementCount > MAX_ENTRIES)
    list.removeChild(list.firstChild);
}

function updateBadge() {
  const badge = document.getElementById('logBadge');
  if (!badge) return;
  if (unseenErrors > 0) {
    badge.textContent = unseenErrors > 99 ? '99+' : String(unseenErrors);
    badge.classList.add('visible');
  } else {
    badge.classList.remove('visible');
  }
}

function isLogsCollapsed() {
  return document.querySelector('[data-panel="logs"]')?.classList.contains('collapsed') ?? false;
}

export function clearBadge() {
  unseenErrors = 0;
  updateBadge();
}

export function initLogs() {
  document.addEventListener('panelOpened', e => {
    if (e.detail === 'logs') clearBadge();
  });

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const level = btn.dataset.level;
      if (activeFilters.has(level)) {
        activeFilters.delete(level);
        btn.classList.remove('active');
      } else {
        activeFilters.add(level);
        btn.classList.add('active');
      }
      applyFilters();
    });
  });

  document.getElementById('clearLogsBtn')?.addEventListener('click', () => {
    const list = document.getElementById('logList');
    if (list) list.innerHTML = '';
    clearBadge();
  });
}

function applyFilters() {
  document.querySelectorAll('#logList .log-row').forEach(row => {
    row.classList.toggle('hidden', !activeFilters.has(row.dataset.level));
  });
}

export function appendLogs(entries) {
  const list = document.getElementById('logList');
  if (!list) return;

  const wasAtBottom = isAtBottom(list);

  entries.forEach(e => {
    if (isLogsCollapsed() && (e.level === 'ERR' || e.level === 'WRN' || e.level === 'FTL')) {
      unseenErrors++;
    }

    const row = document.createElement('div');
    row.className  = `log-row${activeFilters.has(e.level) ? '' : ' hidden'}`;
    row.dataset.level = e.level;

    const colour = COLOURS[e.level] ?? '#ddd';
    row.innerHTML =
      `<span class="log-time">${e.timestamp}</span>` +
      `<span class="log-level ${e.level.toLowerCase()}" style="color:${colour}">${e.level}</span>` +
      `<span class="log-src">${escHtml(e.source)}</span>` +
      `<span class="log-msg">${escHtml(e.message)}</span>`;

    list.appendChild(row);
  });

  enforceMax(list);

  if (entries.length > 0) {
    const last = entries[entries.length - 1];
    const lastLine = document.getElementById('logsLastLine');
    if (lastLine) lastLine.textContent = `[${last.level}] ${last.message}`;
  }

  updateBadge();

  if (wasAtBottom) list.scrollTop = list.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
