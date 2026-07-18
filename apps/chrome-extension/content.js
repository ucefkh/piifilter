/**
 * PIIFilter — Content Script
 * Intercepts prompt submissions on ChatGPT, Claude, Gemini, and Perplexity.
 * Sends prompt text to background script for PII filtering before submission.
 */

(function() {
  'use strict';

  let isActive = true;
  let mode = 'semantic';

  // Load config from storage
  chrome.storage.sync.get({ active: true, mode: 'semantic' }, (config) => {
    isActive = config.active;
    mode = config.mode;
  });

  // Listen for config updates
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.active) isActive = changes.active.newValue;
    if (changes.mode) mode = changes.mode.newValue;
  });

  /**
   * Find the prompt textarea/input on the current page.
   * Works across ChatGPT, Claude, Gemini, and Perplexity.
   */
  function findPromptElement() {
    const selectors = [
      // ChatGPT
      '#prompt-textarea',
      'textarea[data-id="root"]',
      // ChatGPT new
      'div[contenteditable="true"][role="textbox"]',
      // Claude
      'div[contenteditable="true"].ProseMirror',
      'textarea[placeholder*="message"]',
      'div[role="textbox"][contenteditable="true"]',
      // Gemini
      'textarea.ql-editor',
      'div.ql-editor[contenteditable="true"]',
      // Perplexity
      'textarea[data-testid="search-input"]',
      'textarea[placeholder*="Ask"]',
      // Generic
      'textarea[aria-label*="prompt"]',
      'textarea[aria-label*="message"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  /**
   * Find the submit button on the current platform.
   */
  function findSubmitButton() {
    const selectors = [
      'button[data-testid="send-button"]',
      'button[aria-label*="Send"]',
      'button[aria-label*="Submit"]',
      'button:has(svg[data-icon="send"])',
      'button:has(svg.lucide-send)',
      // Claude submit
      'button[aria-label*="Send message"]',
    ];

    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) return btn;
    }
    return null;
  }

  /**
   * Get text content from a prompt element (handles both textarea and contenteditable).
   */
  function getPromptText(element) {
    if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
      return element.value;
    }
    // Contenteditable div
    return element.textContent || element.innerText || '';
  }

  /**
   * Set text content on a prompt element.
   */
  function setPromptText(element, text) {
    if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
      // Use native input setter to trigger React onChange
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value'
      ).set;
      nativeInputValueSetter.call(element, text);
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      // Contenteditable — clear and set new text
      element.innerHTML = '';
      const textNode = document.createTextNode(text);
      element.appendChild(textNode);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  /**
   * Intercept Enter key / submit button clicks.
   * Capture prompt text, send to PIIFilter, replace with filtered version.
   */
  function interceptSubmit(originalSubmitter) {
    return async function(event) {
      const promptEl = findPromptElement();
      if (!promptEl || !isActive) {
        // If inactive or no prompt element, let original behavior proceed
        if (originalSubmitter) return originalSubmitter.call(this, event);
        return;
      }

      const promptText = getPromptText(promptEl);
      if (!promptText || promptText.trim().length < 3) {
        if (originalSubmitter) return originalSubmitter.call(this, event);
        return;
      }

      // Send to background script for filtering
      try {
        const response = await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            { type: 'FILTER_PROMPT', payload: promptText },
            resolve
          );
        });

        if (response && response.filtered && response.filtered !== promptText) {
          // Replace with filtered version
          setPromptText(promptEl, response.filtered);

          // Brief delay for React state to update, then submit
          setTimeout(() => {
            if (originalSubmitter) originalSubmitter.call(this, event);
          }, 50);

          // Show visual indicator
          showFilterIndicator(response.entities?.length || 0, response.risk?.score);
          return;
        }
      } catch (err) {
        console.warn('PIIFilter: Filter error, submitting original:', err.message);
      }

      // No filtering needed or error — proceed normally
      if (originalSubmitter) originalSubmitter.call(this, event);
    };
  }

  /**
   * Show a brief visual indicator that filtering happened.
   */
  function showFilterIndicator(entityCount, riskScore) {
    const existing = document.getElementById('piifilter-indicator');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'piifilter-indicator';
    div.style.cssText = `
      position: fixed;
      top: 8px;
      right: 8px;
      z-index: 999999;
      background: #059669;
      color: white;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      opacity: 0;
      transition: opacity 0.3s ease;
      pointer-events: none;
    `;
    div.textContent = `🛡️ ${entityCount} entities filtered${riskScore ? ` · risk ${Math.round(riskScore)}%` : ''}`;
    document.body.appendChild(div);

    requestAnimationFrame(() => { div.style.opacity = '1'; });

    setTimeout(() => {
      div.style.opacity = '0';
      setTimeout(() => div.remove(), 300);
    }, 2500);
  }

  /**
   * Hook into the page — intercept submit buttons and keyboard events.
   */
  function initialize() {
    // Intercept submit button clicks
    const originalAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
      if (this.tagName === 'BUTTON' && type === 'click') {
        const wrapped = interceptSubmit(listener);
        return originalAddEventListener.call(this, type, wrapped, options);
      }
      return originalAddEventListener.call(this, type, listener, options);
    };

    // Intercept Enter key in the prompt
    document.addEventListener('keydown', async (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
        const promptEl = findPromptElement();
        if (!promptEl || !isActive || !promptEl.matches(':focus')) return;

        const promptText = getPromptText(promptEl);
        if (!promptText || promptText.trim().length < 3) return;

        event.preventDefault();
        event.stopPropagation();

        try {
          const response = await new Promise((resolve) => {
            chrome.runtime.sendMessage(
              { type: 'FILTER_PROMPT', payload: promptText },
              resolve
            );
          });

          if (response && response.filtered && response.filtered !== promptText) {
            setPromptText(promptEl, response.filtered);
            showFilterIndicator(response.entities?.length || 0, response.risk?.score);

            // Re-trigger Enter after filter
            setTimeout(() => {
              const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                shiftKey: false,
                ctrlKey: false,
                metaKey: false,
                bubbles: true,
              });
              promptEl.dispatchEvent(enterEvent);
            }, 100);
          } else {
            // No filter needed, re-dispatch
            promptEl.dispatchEvent(new KeyboardEvent('keydown', {
              key: 'Enter',
              code: 'Enter',
              bubbles: true,
            }));
          }
        } catch {
          promptEl.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            bubbles: true,
          }));
        }
      }
    });
  }

  // Initialize on page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }
})();