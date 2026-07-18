/**
 * PIIFilter — Popup Script
 * Manages the extension popup UI and communicates with background script.
 */

document.addEventListener('DOMContentLoaded', () => {
  const activeToggle = document.getElementById('activeToggle');
  const modeSelect = document.getElementById('modeSelect');
  const thresholdSelect = document.getElementById('thresholdSelect');
  const filteredCount = document.getElementById('filteredCount');
  const riskScore = document.getElementById('riskScore');
  const latency = document.getElementById('latency');
  const scanPage = document.getElementById('scanPage');
  const openServer = document.getElementById('openServer');
  const statusDot = document.getElementById('statusDot');

  // Load config from background
  chrome.runtime.sendMessage({ type: 'GET_CONFIG' }, (config) => {
    if (config) {
      activeToggle.checked = config.active !== false;
      modeSelect.value = config.mode || 'semantic';
      thresholdSelect.value = config.threshold || 'medium';
    }
  });

  // Load stats
  chrome.runtime.sendMessage({ type: 'GET_STATS' }, (stats) => {
    if (stats && stats.filteredCount) {
      filteredCount.textContent = stats.filteredCount;
    }
  });

  // Check health
  chrome.runtime.sendMessage({ type: 'CHECK_HEALTH' }, (health) => {
    if (health && health.healthy) {
      statusDot.classList.remove('off');
    } else {
      statusDot.classList.add('off');
    }
  });

  // Listen for filter updates
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'FILTER_COMPLETE') {
      filteredCount.textContent = msg.payload.filteredCount || '0';
      if (msg.payload.risk) riskScore.textContent = `${Math.round(msg.payload.risk)}%`;
      if (msg.payload.latency) latency.textContent = `${msg.payload.latency}ms`;
    }
  });

  // Save toggle state
  activeToggle.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'SET_CONFIG',
      payload: { active: activeToggle.checked },
    });
  });

  // Save mode
  modeSelect.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'SET_CONFIG',
      payload: { mode: modeSelect.value },
    });
  });

  // Save threshold
  thresholdSelect.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'SET_CONFIG',
      payload: { threshold: thresholdSelect.value },
    });
  });

  // Scan page button
  scanPage.addEventListener('click', () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      chrome.tabs.sendMessage(tabs[0].id, { type: 'SCAN_PAGE' });
      window.close();
    });
  });

  // Open PIIFilter server URL
  openServer.addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://127.0.0.1:8000/docs' });
  });
});