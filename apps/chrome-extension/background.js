// PIIFilter v2 — Background Service Worker
// Manifest V3: handles filter API calls, health checks, configuration

const FILTER_API = 'http://127.0.0.1:8000/v1/filter';
const HEALTH_API = 'http://127.0.0.1:8000/v1/health';
const DEFAULT_CONFIG = { active: true, mode: 'semantic', filteredCount: 0, lastRisk: 'none', lastLatency: 0 };

let filterStats = { ...DEFAULT_CONFIG };
let serverOnline = false;
let healthCheckInterval = null;

// ── Initialisation ──────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  const { config } = await chrome.storage.sync.get('config');
  if (!config) {
    await chrome.storage.sync.set({ config: DEFAULT_CONFIG });
  }
  startHealthCheck();
  updateBadge();
});

chrome.runtime.onStartup.addListener(() => {
  startHealthCheck();
  updateBadge();
});

// ── Health checks ───────────────────────────────────────────────────────────

function startHealthCheck() {
  if (healthCheckInterval) clearInterval(healthCheckInterval);
  checkHealth();
  healthCheckInterval = setInterval(checkHealth, 30000);
}

async function checkHealth() {
  try {
    const resp = await fetch(HEALTH_API, { signal: AbortSignal.timeout(5000) });
    serverOnline = resp.ok;
  } catch {
    serverOnline = false;
  }
  updateBadge();
  // Notify popup if open
  try {
    await chrome.runtime.sendMessage({ type: 'HEALTH_UPDATE', online: serverOnline });
  } catch {
    // popup not open — fine
  }
}

function updateBadge() {
  const colour = serverOnline ? '#22c55e' : '#ef4444'; // green / red
  const text = serverOnline ? 'ON' : 'OFF';
  chrome.action.setBadgeBackgroundColor({ color: colour });
  chrome.action.setBadgeText({ text });
}

// ── Message handler ─────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'FILTER_PROMPT':
      handleFilterPrompt(message.payload, sendResponse);
      return true; // keep channel open for async
    case 'GET_CONFIG':
      chrome.storage.sync.get('config', (result) => sendResponse(result.config || DEFAULT_CONFIG));
      return true;
    case 'SET_CONFIG':
      chrome.storage.sync.set({ config: message.payload }, () => {
        if (message.payload.active !== undefined) filterStats.active = message.payload.active;
        if (message.payload.mode !== undefined) filterStats.mode = message.payload.mode;
        sendResponse({ ok: true });
      });
      return true;
    case 'GET_STATS':
      sendResponse({ ...filterStats, serverOnline });
      return true;
    case 'CHECK_HEALTH':
      checkHealth().then(() => sendResponse({ online: serverOnline }));
      return true;
    default:
      return false;
  }
});

// ── Filter API call ─────────────────────────────────────────────────────────

async function handleFilterPrompt(prompt, sendResponse) {
  const { config } = await chrome.storage.sync.get('config');
  if (!config || !config.active) {
    // Filtering is disabled — pass through
    sendResponse({ filtered: prompt, risk: 'none', entities: [], latency: 0, bypassed: true });
    return;
  }

  const mode = config.mode || 'semantic';
  const start = performance.now();

  try {
    const resp = await fetch(FILTER_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, mode }),
      signal: AbortSignal.timeout(15000),
    });

    const latency = Math.round(performance.now() - start);

    if (!resp.ok) {
      const text = await resp.text().catch(() => 'Unknown error');
      console.warn(`[PIIFilter] API returned ${resp.status}: ${text}`);
      sendResponse({ filtered: prompt, risk: 'unknown', entities: [], latency, error: `HTTP ${resp.status}` });
      return;
    }

    const data = await resp.json();
    const filtered = data.filtered || prompt;
    const risk = data.risk || 'none';
    const entities = data.entities || [];

    // Update stats
    filterStats.filteredCount = (filterStats.filteredCount || 0) + 1;
    filterStats.lastRisk = risk;
    filterStats.lastLatency = latency;
    await chrome.storage.sync.set({ config: { ...config, ...filterStats } });

    sendResponse({ filtered, risk, entities, latency });
  } catch (err) {
    const latency = Math.round(performance.now() - start);
    console.warn(`[PIIFilter] API call failed:`, err.message);
    sendResponse({
      filtered: prompt,
      risk: 'error',
      entities: [],
      latency,
      error: err.message || 'Server unreachable',
    });
  }
}