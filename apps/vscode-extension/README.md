# PIIFilter — VSCode Extension

> **Local-first AI privacy gateway for VSCode.** Intercepts prompts before they reach AI coding assistants (Copilot, Continue.dev, Cody, Cursor) and filters sensitive information through a local PIIFilter REST API.

---

## Features

- **Prompt interception** — Captures text changes and document saves, filtering them through PIIFilter before they reach any AI coding tool
- **Status bar indicator** — Shows connection status at a glance (green = connected, yellow = offline, red = disabled)
- **Real-time inline filtering** — Replaces sensitive content in the editor as you type
- **Selection-based filtering** — Select text and PIIFilter replaces it inline
- **On-save protection** — Filters entire document content on save
- **Debounced API calls** — 500ms debounce prevents flooding the server
- **Configurable modes** — `semantic`, `mask`, or `generalize`

## Installation

### Prerequisites

- VSCode ≥ 1.85.0
- [PIIFilter REST API](https://github.com/nousresearch/piifilter) running at `http://127.0.0.1:8000`

### Build from source

```bash
cd apps/vscode-extension

# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Package as .vsix (requires vsce)
npm install -g @vscode/vsce
vsce package

# Install the extension
code --install-extension piifilter-vscode-2.0.0.vsix
```

### Quick manual install

1. `cd apps/vscode-extension && npm install && npm run compile`
2. Copy the `out/` directory to `~/.vscode/extensions/piifilter-vscode/`
3. Reload VSCode

## Configuration

Open VSCode settings (`Ctrl+,`) and search for `piifilter`.

| Setting | Default | Description |
|---|---|---|
| `piifilter.serverUrl` | `http://127.0.0.1:8000` | PIIFilter REST API URL |
| `piifilter.mode` | `semantic` | Filter mode: `semantic`, `mask`, or `generalize` |
| `piifilter.enabled` | `true` | Enable/disable PIIFilter protection |

## Commands

| Command | Description |
|---|---|
| `PIIFilter: Show Filter Status` | Shows current config (enabled, server URL, mode) |

## Architecture

```
┌──────────────────┐     onDidChangeTextDocument     ┌──────────────────┐
│   VSCode Editor  │ ──────────────────────────────►  │  PIIFilter       │
│   (Copilot /     │      Save intercept via          │  Extension       │
│    Continue /    │     onWillSaveTextDocument        │  (debounced)     │
│    Cody / Cursor)│ ◄─────────────────────────────   │                  │
└──────────────────┘     filtered text replaced       └────────┬─────────┘
                                                               │
                                                      POST /v1/filter
                                                               │
                                                               ▼
                                                  ┌──────────────────┐
                                                  │  PIIFilter API   │
                                                  │  127.0.0.1:8000  │
                                                  │  (local server)  │
                                                  └──────────────────┘
```

The extension listens for document changes (`onDidChangeTextDocument`) and save events (`onWillSaveTextDocument`). Text content is sent to `POST /v1/filter` on the local PIIFilter API. If the server is offline, text passes through unchanged — no data leaks.

## Extension Development

```bash
# Watch mode — auto-compile on changes
npm run watch

# Compile once
npm run compile

# Launch extension debugging host
# Press F5 in VSCode after opening this folder
```

## License

MIT — built by [Nous Research](https://nousresearch.com)