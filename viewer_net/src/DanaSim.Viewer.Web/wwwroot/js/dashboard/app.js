import { initPanels }              from './panels.js';
import { initConfig }              from './config.js';
import { initStatus, updateStatus } from './status.js';
import { initLogs,   appendLogs }  from './logs.js';
import { initViewer, updateViewer } from './viewer.js';
import { initRuns }                from './runs.js';

const CFG = window.__DASHBOARD__;

initPanels();
initConfig();
initStatus();
initLogs();
initViewer();
initRuns();

// Status + viewer — poll every second
setInterval(async () => {
  try {
    const s = await fetch(CFG.statusUrl).then(r => r.json());
    updateStatus(s);
    updateViewer(s.activePlayerUrl);
  } catch { /* server may be starting */ }
}, 1000);

// Logs — separate interval, only fetches new entries
let lastLogIndex = 0;
setInterval(async () => {
  try {
    const r = await fetch(`${CFG.logsUrl}?after=${lastLogIndex}`).then(r => r.json());
    if (r.entries?.length) appendLogs(r.entries);
    lastLogIndex = r.lastIndex;
  } catch { /* ignore */ }
}, 1000);
