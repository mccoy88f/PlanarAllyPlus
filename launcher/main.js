import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { initI18n, t, tFormat } from './i18n.js';

const logEl = document.getElementById('log');
const linkEl = document.getElementById('app-link');
const urlArea = document.getElementById('url-area');
const urlLabel = document.getElementById('url-label');
const statusEl = document.getElementById('status');
const appVersionInfoEl = document.getElementById('app-version-info');
const btnUpdate = document.getElementById('btn-update');
const btnReset = document.getElementById('btn-reset');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnRestart = document.getElementById('btn-restart');
const btnClose = document.getElementById('btn-close');
const logContainer = document.getElementById('log-container');
const logToggle = document.getElementById('log-toggle');
const logSection = document.querySelector('.log-section');
const progressArea = document.getElementById('progress-area');
const progressFill = document.getElementById('progress-fill');
const progressStatus = document.getElementById('progress-status');
const repoLink = document.getElementById('repo-link');
const confirmModal = document.getElementById('confirm-modal');
const confirmModalText = document.getElementById('confirm-modal-text');
const confirmYes = document.getElementById('confirm-yes');
const confirmNo = document.getElementById('confirm-no');

const PORT = 8000;
const REPO_URL = 'https://github.com/mccoy88f/PlanarAllyPlus';
let isRestarting = false;
let appIsReady = false;

// ── Custom confirm modal ─────────────────────────────────────────────────────
function showConfirm(message) {
  return new Promise((resolve) => {
    confirmModalText.textContent = message;
    confirmModal.setAttribute('aria-hidden', 'false');
    function onYes() { cleanup(); resolve(true); }
    function onNo() { cleanup(); resolve(false); }
    function cleanup() {
      confirmModal.setAttribute('aria-hidden', 'true');
      confirmYes.removeEventListener('click', onYes);
      confirmNo.removeEventListener('click', onNo);
    }
    confirmYes.addEventListener('click', onYes);
    confirmNo.addEventListener('click', onNo);
  });
}

// ── Logging ──────────────────────────────────────────────────────────────────
function appendLog(text, isError = false) {
  const line = document.createElement('span');
  line.textContent = text + '\n';
  if (isError) line.style.color = '#f44336';
  logEl.appendChild(line);
  logEl.parentElement.scrollTop = logEl.parentElement.scrollHeight;
}

function setStatus(text, ok = true) {
  statusEl.textContent = text;
  statusEl.style.color = ok ? '#81c784' : '#ffb74d';
}

// ── Button state ─────────────────────────────────────────────────────────────
function setAppReady(ready) {
  appIsReady = ready;
  // Start is only enabled when app is ready AND server is not running
  btnStart.disabled = !ready || btnStop.disabled === false;
  // Initialize only makes sense when app is present
  btnReset.disabled = !ready;
}

function setRunning(running) {
  btnStart.disabled = running || !appIsReady;
  btnStop.disabled = !running;
  btnRestart.disabled = !running;
  btnUpdate.disabled = running;
  btnReset.disabled = running || !appIsReady;
}

function setStarting(starting) {
  btnStart.disabled = starting;
  btnUpdate.disabled = starting;
  btnReset.disabled = starting;
  btnStop.disabled = !starting;
  btnRestart.disabled = true;
}

// ── Progress bar ─────────────────────────────────────────────────────────────
function showProgress(indeterminate = true, statusText = '') {
  progressArea.classList.add('visible');
  progressFill.classList.toggle('indeterminate', indeterminate);
  progressStatus.textContent = statusText;
}

function hideProgress(success = true, statusText = '') {
  progressFill.classList.remove('indeterminate');
  progressFill.style.width = '100%';
  progressFill.style.background = success ? 'linear-gradient(90deg, #2e7d32, #4caf50)' : '#c62828';
  progressStatus.textContent = statusText || (success ? t('progressUpdateComplete') : t('progressUpdateFailed'));
  setTimeout(() => {
    progressArea.classList.remove('visible');
  }, 1500);
}

// ── Download/Update button label ─────────────────────────────────────────────
function updateBtnUpdateLabel(ready) {
  const key = ready ? 'btnUpdate' : 'btnDownload';
  btnUpdate.textContent = t(key);
  btnUpdate.setAttribute('data-i18n', key);
}

// ── Version info in subtitle ─────────────────────────────────────────────────
async function refreshVersionInfo() {
  try {
    const info = await invoke('get_app_version_info');
    if (info && info.commit) {
      let text = `[${info.commit}`;
      if (info.date) text += ` · ${info.date}`;
      text += ']';
      appVersionInfoEl.textContent = text;
    } else {
      appVersionInfoEl.textContent = '';
    }
  } catch {
    appVersionInfoEl.textContent = '';
  }
}

// ── Status refresh ───────────────────────────────────────────────────────────
async function refreshStatus() {
  try {
    const status = await invoke('get_app_status');
    if (status.ready) {
      setStatus(tFormat('statusReadyPath', { path: status.path }), true);
    } else {
      setStatus(t(status.path), false);
    }
    updateBtnUpdateLabel(status.ready);
    setAppReady(status.ready);
    await refreshVersionInfo();
  } catch (e) {
    setStatus(t('statusErrorPrefix') + t(String(e)), false);
  }
}

async function updateLink() {
  try {
    const ip = await invoke('get_local_ip');
    const url = `http://${ip}:${PORT}`;
    linkEl.textContent = url;
    linkEl.dataset.url = url;
  } catch {
    const url = `http://localhost:${PORT}`;
    linkEl.textContent = url;
    linkEl.dataset.url = url;
  }
}

function showUrlArea() {
  urlArea.classList.remove('hidden');
  urlLabel.textContent = t('urlReachableAt');
}

function hideUrlArea() {
  urlArea.classList.add('hidden');
}

// ── Event listeners ──────────────────────────────────────────────────────────

// Open app URL in default browser
linkEl.addEventListener('click', async (e) => {
  e.preventDefault();
  const url = (linkEl.dataset.url || linkEl.textContent || '').trim();
  if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
    try { await invoke('open_browser_url', { url }); }
    catch (err) { console.error('Failed to open URL:', err); }
  }
});

// Repo link
repoLink.addEventListener('click', async (e) => {
  e.preventDefault();
  try { await invoke('open_browser_url', { url: REPO_URL }); }
  catch (err) { console.error('Failed to open repo URL:', err); }
});

// Collapsible log
logToggle.addEventListener('click', () => {
  const expanded = logContainer.classList.toggle('collapsed');
  logSection.classList.toggle('expanded', !expanded);
  logToggle.querySelector('.log-toggle-text').textContent = expanded ? t('logShow') : t('logHide');
  logToggle.setAttribute('aria-expanded', !expanded);
});

// Server events
listen('server-log', (event) => { appendLog(event.payload, false); });
listen('server-log-err', (event) => { appendLog(event.payload, true); });

listen('server-started', () => {
  isRestarting = false;
  setRunning(true);
  appendLog('--- Server started ---');
  showUrlArea();
  updateLink();
  hideProgress(true, t('progressServerReady'));
});

listen('server-stopped', (event) => {
  if (!isRestarting) {
    setRunning(false);
    hideUrlArea();
  }
  appendLog(`--- Server stopped (exit: ${event.payload}) ---`);
});

listen('download-progress', (event) => {
  const msgKey = event.payload;
  // If we don't have a translation (e.g., error string), fallback to the string itself
  const msg = t(msgKey);
  setStatus(msg, true);
  progressStatus.textContent = msg;
  appendLog(msg);
});

// Download / Update button
btnUpdate.addEventListener('click', async () => {
  logEl.textContent = '';
  if (!logContainer.classList.contains('collapsed')) {
    logContainer.classList.add('collapsed');
    logSection.classList.remove('expanded');
    logToggle.querySelector('.log-toggle-text').textContent = t('logShow');
  }
  showProgress(true, t('progressDownloading'));
  btnUpdate.disabled = true;
  btnReset.disabled = true;
  try {
    const path = await invoke('ensure_app_downloaded', { force: true });
    appendLog('Completed: ' + path);
    await refreshStatus();
    hideProgress(true, t('progressUpdateComplete'));
  } catch (e) {
    appendLog('Error: ' + String(e), true);
    hideProgress(false, t('progressUpdateFailed'));
    await refreshStatus();
  }
});

// Initialize (reset) button — uses custom modal instead of confirm()
btnReset.addEventListener('click', async () => {
  const confirmed = await showConfirm(t('initializeConfirm'));
  if (!confirmed) return;
  showProgress(true, t('progressInitializing'));
  btnReset.disabled = true;
  btnUpdate.disabled = true;
  try {
    await invoke('reset_app');
    appendLog('App reset: installation folder removed.');
    await refreshStatus();
    hideProgress(true, t('progressInitializeComplete'));
  } catch (e) {
    appendLog('Reset error: ' + String(e), true);
    hideProgress(false, t('progressInitializeFailed'));
    await refreshStatus();
  }
});

// Start server
btnStart.addEventListener('click', async () => {
  logEl.textContent = '';
  if (!logContainer.classList.contains('collapsed')) {
    logContainer.classList.add('collapsed');
    logSection.classList.remove('expanded');
    logToggle.querySelector('.log-toggle-text').textContent = t('logShow');
  }
  showProgress(true, t('progressPreparing'));
  setStarting(true);
  try {
    await invoke('start_server', { mode: 'full' });
  } catch (e) {
    appendLog('Error: ' + String(e), true);
    await refreshStatus();
    hideProgress(false, t('progressStartFailed'));
    setRunning(false);
  }
});

// Stop server
btnStop.addEventListener('click', async () => {
  try { await invoke('stop_server'); }
  catch (e) { appendLog('Stop error: ' + String(e), true); }
});

// Close application
btnClose.addEventListener('click', async () => {
  try { await invoke('exit_app'); }
  catch (e) { appendLog('Error: ' + String(e), true); }
});

// Restart server
btnRestart.addEventListener('click', async () => {
  logEl.textContent = '';
  showProgress(true, t('progressRestarting'));
  isRestarting = true;
  setStarting(true);
  try {
    await invoke('restart_server');
  } catch (e) {
    appendLog('Error: ' + String(e), true);
    hideProgress(false, t('progressRestartFailed'));
    setRunning(false);
    isRestarting = false;
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────
async function main() {
  await initI18n();
  try {
    const ver = await invoke('get_launcher_version');
    document.getElementById('launcher-version').textContent = `v${ver}`;
  } catch {
    document.getElementById('launcher-version').textContent = '';
  }
  await refreshStatus();
}
main();
