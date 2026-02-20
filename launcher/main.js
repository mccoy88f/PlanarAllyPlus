import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { initI18n, t, tFormat } from './i18n.js';

const logEl = document.getElementById('log');
const linkEl = document.getElementById('app-link');
const urlArea = document.getElementById('url-area');
const urlLabel = document.getElementById('url-label');
const statusEl = document.getElementById('status');
const btnUpdate = document.getElementById('btn-update');
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

const PORT = 8000;
let isRestarting = false;

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

function setRunning(running) {
  btnStart.disabled = running;
  btnStop.disabled = !running;
  btnRestart.disabled = !running;
  btnUpdate.disabled = running;
}

function setStarting(starting) {
  btnStart.disabled = starting;
  btnUpdate.disabled = starting;
  btnStop.disabled = !starting;
  btnRestart.disabled = true;
}

function showProgress(indeterminate = true, statusText = '') {
  progressArea.classList.add('visible');
  progressFill.classList.toggle('indeterminate', indeterminate);
  progressStatus.textContent = statusText;
}

function hideProgress(success = true, statusText = '') {
  progressFill.classList.remove('indeterminate');
  progressFill.style.width = success ? '100%' : '100%';
  progressFill.style.background = success ? 'linear-gradient(90deg, #2e7d32, #4caf50)' : '#c62828';
  progressStatus.textContent = statusText || (success ? t('progressUpdateComplete') : t('progressUpdateFailed'));
  setTimeout(() => {
    progressArea.classList.remove('visible');
  }, 1500);
}

async function refreshStatus() {
  try {
    const status = await invoke('get_app_status');
    if (status.ready) {
      setStatus(tFormat('statusReadyPath', { path: status.path }), true);
    } else {
      setStatus(status.path, false);
    }
  } catch (e) {
    setStatus(t('statusErrorPrefix') + e, false);
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

// Open URL in default browser when clicking the link
linkEl.addEventListener('click', async (e) => {
  e.preventDefault();
  const url = (linkEl.dataset.url || linkEl.textContent || '').trim();
  if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
    try {
      await invoke('open_browser_url', { url });
    } catch (err) {
      console.error('Failed to open URL:', err);
    }
  }
});

// Collapsible log
logToggle.addEventListener('click', () => {
  const expanded = logContainer.classList.toggle('collapsed');
  logSection.classList.toggle('expanded', !expanded);
  logToggle.querySelector('.log-toggle-text').textContent = expanded ? t('logShow') : t('logHide');
  logToggle.setAttribute('aria-expanded', !expanded);
});

listen('server-log', (event) => {
  appendLog(event.payload, false);
});

listen('server-log-err', (event) => {
  appendLog(event.payload, true);
});

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
  const msg = event.payload;
  setStatus(msg, true);
  progressStatus.textContent = msg;
  appendLog(msg);
});

btnUpdate.addEventListener('click', async () => {
  logEl.textContent = '';
  if (!logContainer.classList.contains('collapsed')) {
    logContainer.classList.add('collapsed');
    logSection.classList.remove('expanded');
    logToggle.querySelector('.log-toggle-text').textContent = t('logShow');
  }
  showProgress(true, t('progressDownloading'));
  btnUpdate.disabled = true;
  try {
    const path = await invoke('ensure_app_downloaded', { force: true });
    appendLog('Completed: ' + path);
    refreshStatus();
    hideProgress(true, t('progressUpdateComplete'));
  } catch (e) {
    appendLog('Error: ' + String(e), true);
    hideProgress(false, t('progressUpdateFailed'));
  }
  btnUpdate.disabled = btnStart.disabled; // keep disabled if server is running
});

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
    refreshStatus();
    hideProgress(false, t('progressStartFailed'));
    setRunning(false);
  }
});

btnStop.addEventListener('click', async () => {
  try {
    await invoke('stop_server');
  } catch (e) {
    appendLog('Stop error: ' + String(e), true);
  }
});

btnClose.addEventListener('click', async () => {
  try {
    await invoke('exit_app');
  } catch (e) {
    appendLog('Error: ' + String(e), true);
  }
});

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

async function main() {
  await initI18n();
  statusEl.textContent = t('loading');
  try {
    const ver = await invoke('get_launcher_version');
    document.getElementById('launcher-version').textContent = `v${ver}`;
  } catch {
    document.getElementById('launcher-version').textContent = '';
  }
  refreshStatus();
}
main();
