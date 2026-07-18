// PIIFilter v2 — Popup Script
// Manages extension config, displays stats, health checks

document.addEventListener('DOMContentLoaded', async () => {
  // ── Element refs ──────────────────────────────────────────────────────────
  const toggleActive    = document.getElementById('toggleActive');
  const modeSelect      = document.getElementById('modeSelect');
  const filteredCount   = document.getElementById('filteredCount');
  const lastRisk        = document.getElementById('lastRisk');
  const lastLatency     = document.getElementById('lastLatency');
  const serverStatus    = document.getElementById('serverStatus');
  const statusDot       = document.getElementById('statusDot');
  const btnScan         = document.getElementById('btnScan');
  const btnDocs         = document.getElementById('btnDocs');
  const linkDocs        = document.getElementById('linkDocs');
  const versionEl       = document.getElementById('version');

  // ── Load config ───────────────────────────────────────────────────────────
  async function loadConfig() {
    const config = await chrome.runtime.sendMessage({ type: 'GET_CONFIG' });
    if (config) {
      toggleActive.checked = config.active !== false;
      modeSelect.value = config.mode || 'semantic';
      // Load stats if stored
      if (config.filteredCount !== undefined) filteredCount.textContent = config.filteredCount;
      if (config.lastRisk) {
        lastRisk.textContent = config.lastRisk;
        setRiskClass(lastRisk, config.lastRisk);
      }
      if (config.lastLatency) lastLatency.textContent = `${config.lastLatency}ms`;
    }
  }

  // ── Health check ──────────────────────────────────────────────────────────
  async function checkHealth() {
    const result = await chrome.runtime.sendMessage({ type: 'CHECK_HEALTH' });
    updateServerUI(result ? result.online : false);
  }

  function updateServerUI(online) {
    statusDot.className = `status-dot ${online ? 'online' : 'offline'}`;
    serverStatus.textContent = online ? 'ON' : 'OFF';
    serverStatus.style.color = online ? '#22c55e' : '#ef4444';
  }

  // ── Stats update listener ─────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'HEALTH_UPDATE') {
      updateServerUI(message.online);
    }
  });

  // ── Risk label styling ────────────────────────────────────────────────────
  function setRiskClass(el, risk) {
    el.className = 'stat-value stat-risk';
    if (['low', 'none', 'unknown'].includes(risk)) el.classList.add('low');
    else if (risk === 'medium') el.classList.add('medium');
    else if (risk === 'high') el.classList.add('high');
    else if (['critical', 'error'].includes(risk)) el.classList.add('critical');
  }

  // ── Save config helpers ───────────────────────────────────────────────────
  async function saveConfig() {
    const config = {
      active: toggleActive.checked,
      mode: modeSelect.value,
    };
    await chrome.runtime.sendMessage({ type: 'SET_CONFIG', payload: config });
  }

  toggleActive.addEventListener('change', saveConfig);
  modeSelect.addEventListener('change', saveConfig);

  // ── Actions ───────────────────────────────────────────────────────────────
  btnScan.addEventListener('click', async () => {
    // Query the active tab and send a scan request
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, { type: 'SCAN_PAGE' }).catch(() => {
        // content script not loaded on this page — that's fine
      });
    }
    window.close();
  });

  btnDocs.addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://piifilter.dev/docs' });
  });

  linkDocs.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://piifilter.dev/docs' });
  });

  // ── Init ──────────────────────────────────────────────────────────────────
  await loadConfig();
  await checkHealth();
});