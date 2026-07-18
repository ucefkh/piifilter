/**
 * PIIFilter — Chrome Extension Background Service Worker
 * Intercepts prompts and sends them to local PIIFilter server.
 */

const PIIFILTER_ENDPOINT = 'http://127.0.0.1:8000/filter';
const PIIFILTER_HEALTH = 'http://127.0.0.1:8000/health';
const DEFAULT_CONFIG = {
  active: true,
  mode: 'semantic',
  threshold: 'medium',
};

let filteredCount = 0;
let config = { ...DEFAULT_CONFIG };

// Load saved config
chrome.storage.sync.get(DEFAULT_CONFIG, (saved) => {
  config = { ...DEFAULT_CONFIG, ...saved };
});

// Listen for config changes
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'GET_CONFIG') {
    sendResponse(config);
  } else if (msg.type === 'SET_CONFIG') {
    config = { ...config, ...msg.payload };
    chrome.storage.sync.set(config);
    sendResponse({ success: true });
  } else if (msg.type === 'GET_STATS') {
    sendResponse({ filteredCount });
  } else if (msg.type === 'FILTER_PROMPT') {
    filterPrompt(msg.payload, sendResponse);
    return true; // Keep channel open for async response
  } else if (msg.type === 'CHECK_HEALTH') {
    checkHealth(sendResponse);
    return true;
  }
});

/**
 * Send a prompt to the local PIIFilter server for filtering.
 */
async function filterPrompt(prompt, sendResponse) {
  if (!config.active) {
    // If inactive, return prompt unchanged with zero entities
    sendResponse({ filtered: prompt, risk: null, entities: [], latency: 0 });
    return;
  }

  const start = performance.now();

  try {
    const response = await fetch(PIIFILTER_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        mode: config.mode,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();
    const latency = performance.now() - start;

    filteredCount++;
    chrome.storage.sync.set({ filteredCount });

    // Notify popup about update
    chrome.runtime.sendMessage({
      type: 'FILTER_COMPLETE',
      payload: { filteredCount, risk: data.risk?.score, latency: Math.round(data.latency_ms) },
    });

    sendResponse({
      filtered: data.filtered,
      risk: data.risk,
      entities: data.entities,
      replacements: data.replacements,
      latency: Math.round(data.latency_ms),
    });
  } catch (err) {
    console.warn('PIIFilter: Server unreachable, bypassing filter.', err.message);
    sendResponse({
      filtered: prompt,
      risk: null,
      entities: [],
      latency: performance.now() - start,
      error: 'PIIFilter server unreachable. Running without filtering.',
    });
  }
}

/**
 * Check if the PIIFilter server is healthy.
 */
async function checkHealth(sendResponse) {
  try {
    const response = await fetch(PIIFILTER_HEALTH);
    const data = await response.json();
    sendResponse({ healthy: true, ...data });
  } catch {
    sendResponse({ healthy: false });
  }
}

// Periodic health check
setInterval(async () => {
  try {
    const res = await fetch(PIIFILTER_HEALTH);
    if (res.ok) {
      chrome.action.setBadgeText({ text: 'ON' });
      chrome.action.setBadgeBackgroundColor({ color: '#22c55e' });
    }
  } catch {
    chrome.action.setBadgeText({ text: 'OFF' });
    chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
  }
}, 30000);