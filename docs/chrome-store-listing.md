# PIIFilter — Chrome Web Store Listing

## Title

**PIIFilter — Local AI Privacy Gateway**

## Short Description

Protect your privacy when using ChatGPT, Claude, and Gemini. PIIFilter strips personal data from prompts before they reach AI models — all running locally. (132 chars ✓)

## Full Description

**PIIFilter is a local-first AI privacy gateway for Chrome.** It runs as a browser extension that intercepts prompts sent to ChatGPT, Claude, Gemini, and Perplexity, filters out personally identifiable information (PII) before the data reaches the LLM provider, and returns a cleaned prompt — all on your machine.

### How It Works

1. You type a prompt into ChatGPT, Claude, Gemini, or Perplexity
2. PIIFilter intercepts the prompt before it leaves your browser
3. The extension sends the prompt to your local PIIFilter API server running at `127.0.0.1:8000`
4. The API scrubs PII (names, emails, phone numbers, addresses, SSNs, credit cards, etc.)
5. The cleaned prompt is submitted to the AI provider — your personal data stays local

### Key Features

- **🧠 Three Filtering Modes:**
  - **Semantic (default)** — Context-aware PII removal that preserves natural language flow
  - **Mask** — Replaces detected PII with placeholder tokens (e.g., `[NAME_1]`, `[EMAIL]`)
  - **Generalize** — Replaces specific values with broad categories (e.g., `[email address]`)

- **🔒 Local-First Architecture** — All PII detection and filtering runs on your own machine. No cloud dependency, no third-party data sharing, no telemetry.

- **🏠 Self-Hosted Backend** — PIIFilter pairs with a lightweight Python/FastAPI server. Full source available, fully auditable, fully under your control.

- **📊 Real-Time Dashboard** — The popup shows filtering stats: prompts filtered, last risk level, server health, and latency. Toggle filtering on/off in one click.

- **🔄 Supported Platforms:**
  - ChatGPT (chatgpt.com, chat.openai.com)
  - Claude (claude.ai)
  - Google Gemini (gemini.google.com)
  - Perplexity (perplexity.ai)

- **⚙️ Configurable** — Enable/disable filtering on the fly, switch between modes, and monitor your privacy in real time.

### Who Is It For?

- Privacy-conscious professionals who use AI coding assistants with sensitive codebases
- Healthcare, legal, and finance workers who need to discuss confidential information with AI
- Anyone who wants full control over what personal data leaves their machine
- Developers who want an auditable, self-hosted privacy layer for LLM interactions

### Requirements

- Local PIIFilter API server running on `http://127.0.0.1:8000` (setup instructions at the GitHub repo)
- Chrome or Chromium-based browser

---

## Screenshots

> **Note:** Replace these placeholder paths with actual screenshots before submitting to the Chrome Web Store.

| Screenshot | Description |
|---|---|
| `screenshots/popup-dashboard.png` | Main popup showing filtering toggle, mode selector, and session stats (filtered count, risk level, latency, server status) |
| `screenshots/semantic-mode.png` | Example of semantic filtering — a prompt with PII before and after processing |
| `screenshots/settings-view.png` | Settings panel showing filtering mode options and configuration |
| `screenshots/server-health.png` | Health indicator showing server online/offline state with green/red badge |

### Screenshot Requirements (Chrome Web Store)

- **Dimensions:** 1280×800 or 640×400
- **Format:** PNG or JPEG
- **Max size:** 2 MB each
- **At least 1 screenshot required** (recommended: 4–5)
- Caption each screenshot to explain what the user is seeing

---

## Privacy Policy Summary

**PIIFilter does not collect, transmit, or store your personal data.**

- All PII detection and filtering runs **locally** on your machine via a self-hosted API server
- The extension communicates only with `http://127.0.0.1:8000` (your local server)
- No data is ever sent to third-party servers, analytics services, or external APIs
- No user accounts, no telemetry, no cookies, no tracking
- The extension requests only the permissions necessary to function (see Permissions Justification below)
- Full source code is available for audit at the project repository

Your prompts are processed in real time on your own hardware. What you type stays with you.

---

## Permissions Justification

| Permission | Why Needed |
|---|---|
| **`storage`** | Stores your filtering preferences (on/off state, selected mode) and session statistics (prompts filtered, last risk level) using `chrome.storage.sync`. No data is synced to Google's servers unless you have Chrome sync enabled — and even then, only non-sensitive configuration data is stored. |
| **`https://chatgpt.com/*`** | Content script injection and prompt interception on ChatGPT |
| **`https://chat.openai.com/*`** | Content script injection and prompt interception on ChatGPT legacy URLs |
| **`https://claude.ai/*`** | Content script injection and prompt interception on Claude |
| **`https://gemini.google.com/*`** | Content script injection and prompt interception on Google Gemini |
| **`https://*.perplexity.ai/*`** | Content script injection and prompt interception on Perplexity |
| **`http://127.0.0.1:8000/*`** | Host permission to send filtered prompts to your local PIIFilter API server. This is a loopback address — no external network traffic is generated. |

### Why These Permissions Are Minimal

PIIFilter uses **host permissions** (Manifest V3) scoped to specific AI platform URLs plus localhost. It does **not** request `<all_urls>` or broad `*://*/*` access. The `storage` permission is limited to configuration only — no browsing history, no tabs, no network request interception beyond the declarative content script matches.