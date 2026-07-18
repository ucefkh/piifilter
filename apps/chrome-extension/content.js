// PIIFilter v2 — Content Script
// Intercepts prompt submissions on ChatGPT, Claude, Gemini, Perplexity
// Sends to background service worker for filtering, replaces text, submits

// ── Platform detection ──────────────────────────────────────────────────────

const PLATFORM = (() => {
  const host = window.location.hostname;
  if (host === 'chatgpt.com' || host === 'chat.openai.com') return 'chatgpt';
  if (host === 'claude.ai') return 'claude';
  if (host === 'gemini.google.com') return 'gemini';
  if (host.endsWith('.perplexity.ai') || host === 'perplexity.ai') return 'perplexity';
  return 'unknown';
})();

// ── Platform-specific selectors ─────────────────────────────────────────────

const SELECTORS = {
  chatgpt: {
    textarea: 'textarea[placeholder*="Message ChatGPT"], #prompt-textarea, textarea:not([aria-hidden])',
    submitBtn: 'button[data-testid="send-button"], button[aria-label*="Send"]',
    contenteditable: '', // ChatGPT uses textarea now
  },
  claude: {
    textarea: '', // Claude uses contenteditable
    submitBtn: 'button[aria-label*="Send"], button[class*="send-button"]',
    contenteditable: '[contenteditable="true"][role="textbox"], .ProseMirror',
  },
  gemini: {
    textarea: 'textarea[placeholder*="Enter"], .ql-editor, textarea.ql-editor',
    submitBtn: 'button[aria-label*="Send"], button.send-button',
    contenteditable: '[contenteditable="true"]',
  },
  perplexity: {
    textarea: 'textarea[placeholder*="Ask"], textarea[placeholder*="Search"]',
    submitBtn: 'button[aria-label*="Submit"], button[type="submit"]',
    contenteditable: '',
  },
};

const sel = SELECTORS[PLATFORM] || SELECTORS.chatgpt;

// ── Toast notification ──────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  const existing = document.querySelector('.piifilter-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'piifilter-toast';
  toast.textContent = message;
  Object.assign(toast.style, {
    position: 'fixed',
    bottom: '80px',
    right: '16px',
    zIndex: '999999',
    padding: '10px 18px',
    borderRadius: '10px',
    fontSize: '14px',
    fontWeight: '600',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
    transition: 'opacity 0.3s ease',
    opacity: '1',
    pointerEvents: 'none',
    backdropFilter: 'blur(8px)',
    color: type === 'error' ? '#f87171' : '#38bdf8',
    background: 'rgba(15, 23, 42, 0.92)',
    border: type === 'error' ? '1px solid rgba(248,113,113,0.3)' : '1px solid rgba(56,189,248,0.3)',
  });

  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 400); }, 3000);
}

// ── Get prompt from the input element ───────────────────────────────────────

function getPromptText() {
  if (PLATFORM === 'claude') {
    const editable = document.querySelector(sel.contenteditable);
    if (editable) return editable.textContent || editable.innerText || '';
  }
  if (PLATFORM === 'gemini') {
    const editable = document.querySelector(sel.contenteditable);
    if (editable && editable.textContent) return editable.textContent || '';
    const ta = document.querySelector(sel.textarea);
    if (ta) return ta.value || '';
  }
  const ta = document.querySelector(sel.textarea);
  if (ta) return ta.value || '';
  return '';
}

// ── Set prompt in the input element ─────────────────────────────────────────

function setPromptText(text) {
  if (PLATFORM === 'claude') {
    const editable = document.querySelector(sel.contenteditable);
    if (!editable) return false;
    editable.textContent = text;
    // Dispatch input event so Claude's react picks it up
    editable.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    editable.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  if (PLATFORM === 'gemini') {
    const editable = document.querySelector(sel.contenteditable);
    if (editable) {
      editable.textContent = text;
      editable.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
      editable.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
    const ta = document.querySelector(sel.textarea);
    if (ta) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value'
      ).set;
      nativeInputValueSetter.call(ta, text);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    }
    return false;
  }
  // ChatGPT / Perplexity — standard textarea
  const ta = document.querySelector(sel.textarea);
  if (!ta) return false;
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, 'value'
  ).set;
  nativeInputValueSetter.call(ta, text);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}

// ── Click the submit button ─────────────────────────────────────────────────

function clickSubmit() {
  const btn = document.querySelector(sel.submitBtn);
  if (btn) {
    btn.click();
    return true;
  }
  // Fallback: try Enter key on textarea
  const ta = document.querySelector(sel.textarea) || document.querySelector(sel.contenteditable);
  if (ta) {
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    return true;
  }
  return false;
}

// ── Main filter + submit logic ──────────────────────────────────────────────

async function filterAndSubmit(originalPrompt) {
  if (!originalPrompt || originalPrompt.trim().length === 0) return;

  try {
    const response = await chrome.runtime.sendMessage({
      type: 'FILTER_PROMPT',
      payload: originalPrompt,
    });

    if (!response) {
      // Popup not open or error — proceed with original
      showToast('⚠️ PIIFilter unavailable, sending original', 'error');
      return;
    }

    if (response.error || response.bypassed) {
      showToast(response.bypassed
        ? '⏸️ PIIFilter paused — sending original'
        : `⚠️ Filter error — sending original (${response.error})`, 'error');
      return;
    }

    const filtered = response.filtered;
    const entityCount = (response.entities || []).length;
    const risk = response.risk || 'none';
    const latency = response.latency || 0;

    if (filtered !== originalPrompt) {
      // Replace textarea content with filtered version
      setPromptText(filtered);
      // Short delay to let React reconcile
      await new Promise(r => setTimeout(r, 100));
    }

    // Show toast
    const toastMsg = entityCount > 0
      ? `🛡️ ${entityCount} PII entit${entityCount === 1 ? 'y' : 'ies'} filtered (${risk}) — ${latency}ms`
      : `✅ Prompt clean (${latency}ms)`;
    showToast(toastMsg);
  } catch (err) {
    console.warn('[PIIFilter] Communication error:', err);
    showToast('⚠️ PIIFilter error — sending original', 'error');
  }
}

// ── Intercept Enter on textarea / contenteditable ───────────────────────────

function interceptEnter(e) {
  // Only intercept plain Enter (not Shift+Enter)
  if (e.key === 'Enter' && !e.shiftKey) {
    const prompt = getPromptText();
    if (prompt && prompt.trim().length > 0) {
      e.preventDefault();
      e.stopPropagation();
      filterAndSubmit(prompt);
    }
  }
}

function setupInterceptor() {
  // Remove existing listeners if any
  const oldInput = document.querySelector(sel.textarea) || document.querySelector(sel.contenteditable);
  if (oldInput) {
    oldInput.removeEventListener('keydown', interceptEnter);
  }

  // Set up keydown interceptor
  const input = document.querySelector(sel.textarea) || document.querySelector(sel.contenteditable);
  if (input) {
    input.addEventListener('keydown', interceptEnter, true);
  }

  // Also intercept button clicks
  const btn = document.querySelector(sel.submitBtn);
  if (btn) {
    btn.addEventListener('click', async (e) => {
      // Small delay to let the UI state settle, then check if we should intercept
      setTimeout(async () => {
        const prompt = getPromptText();
        if (prompt && prompt.trim().length > 0) {
          // Only intercept if the extension is active
          try {
            const { config } = await chrome.storage.sync.get('config');
            if (config && config.active) {
              e.preventDefault();
              e.stopPropagation();
              filterAndSubmit(prompt);
            }
          } catch {
            // continue with normal flow
          }
        }
      }, 50);
    }, true);
  }
}

// ── MutationObserver for SPA navigation ─────────────────────────────────────

function observeDOM() {
  const observer = new MutationObserver(() => {
    const input = document.querySelector(sel.textarea) || document.querySelector(sel.contenteditable);
    const btn = document.querySelector(sel.submitBtn);
    if (input || btn) {
      setupInterceptor();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

// ── Initialise ──────────────────────────────────────────────────────────────

function init() {
  if (PLATFORM === 'unknown') {
    console.warn('[PIIFilter] Unknown platform — not injecting');
    return;
  }
  console.log(`[PIIFilter] Active on ${PLATFORM}`);
  setupInterceptor();
  observeDOM();
}

// Wait for page to be interactive
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}