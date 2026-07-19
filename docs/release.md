# Releasing PIIFilter

## Prerequisites

- PyPI account with API token (configured via `UV_PUBLISH_TOKEN` or `.netrc`)
- GitHub CLI (`gh`) authenticated for changelog/release management
- Node.js and npm for JS/SDK packages

## Steps

### 1. Core Python package

```bash
cd core
uv build
uv publish
```

### 2. SDK Python package

```bash
cd sdk
uv build
uv publish
```

### 3. npm package

```bash
cd sdk/js
npm login
npm publish
```

### 4. Chrome Extension

1. Go to https://chrome.google.com/webstore/devconsole
2. Upload `dist/piifilter-chrome-v2.zip`
3. Fill in the store listing from `docs/chrome-store-listing.md`
4. Submit for review

### 5. GitHub Release

```bash
gh release create v2.0.0 \
  --title "v2.0.0" \
  --notes "Release notes here" \
  --generate-notes
```

## Verification

After publishing, verify each package installs cleanly:

```bash
pip install piifilter
pip install piifilter-sdk
npm install @piifilter/sdk
```

## Troubleshooting

| Issue | Likely Fix |
|-------|------------|
| `uv publish` auth failure | Check `UV_PUBLISH_TOKEN` or `UV_PUBLISH_USER`/`UV_PUBLISH_PASSWORD` |
| Version already exists | Bump version in `pyproject.toml` before publishing |
| npm publish 403 | Ensure you're logged in with `npm whoami` and have package access |