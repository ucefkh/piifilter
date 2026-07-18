# PIIFilter Security

## Threat Model

PIIFilter protects against:
- **Accidental PII leakage** — sensitive data (names, emails, SSNs, API keys, credentials) embedded in LLM prompts that would otherwise be transmitted to third-party providers
- **Credential exposure** — API keys, JWT tokens, database URLs, and SSH keys in chat interfaces or copilot tools
- **Personally identifiable information** — names, addresses, phone numbers, and financial data in shared or logged contexts
- **Sensitive business data** — project names, internal URLs, and customer references in prompts forwarded to external LLMs

PIIFilter does **NOT** protect against:
- Malicious actors with local machine access
- Remote code execution on the host machine
- Compromised LLM providers (filtered prompts still reach the provider)
- Side-channel attacks via timing or response content
- Network-level eavesdropping if the REST API is not bound to localhost
- Prompt injection or jailbreaks that bypass the detection layer

## Attack Surface

### 1. Local API Server (port 8000 by default)

| Concern | Mitigation |
|---------|-----------|
| Network exposure | Binds to `127.0.0.1` — not exposed to LAN/WAN |
| Authentication | Intentional: local-only design. No auth secrets to leak |
| CORS | Disabled for external origins |
| Request size | 100 KB truncation via `truncate_prompt()` |

### 2. Plugin System

| Concern | Mitigation |
|---------|-----------|
| Malicious plugins | Plugins are installed Python packages. Only install from trusted sources |
| Plugin lifecycle | `initialize()` / `shutdown()` called explicitly. Failed plugins are logged, not silently ignored |
| Auto-discovery | `piifilter_` prefix scanning only. No arbitrary code execution |
| Version constraints | `PluginLoader` validates `min_version` requirements |

### 3. Memory

| Concern | Mitigation |
|---------|-----------|
| Prompt data in memory | Held only during pipeline execution; not serialized to disk by default |
| Audit trail | Records metadata only — **no prompt content** in audit events |
| Deterministic aliases | Reversible only within the same process (no persistent mapping stored) |
| Session objects | Short-lived; garbage collected after pipeline completion |

### 4. Transport Methods

| Transport | Exposure |
|-----------|----------|
| CLI | Local process only |
| REST API | Localhost-bound, no auth |
| SDK | In-process, caller owns memory |
| Chrome Extension | Communicates only with `localhost:8000` |
| MCP Server | stdio transport (Claude Desktop) — local only |
| OpenAI Proxy | Not yet implemented — planned as a local-only proxy endpoint |

## Data Flow

```
Prompt → Transport (CLI/API/SDK/MCP/Chrome)
              ↓
         Pipeline
    ┌──────────────────┐
    │ 1. Detect         │  ← Regex, Presidio, GLiNER plugins
    │ 2. Risk Assess    │  ← 0-100 scoring
    │ 3. Policy Engine  │  ← Declarative rules (BLOCK / REPLACE / REVIEW)
    │ 4. Replace        │  ← Semantic / Mask / Generalize strategies
    │ 5. Forward (opt.) │  ← Filtered prompt to LLM provider
    └──────────────────┘
              ↓
         No prompt data persisted by default
         Audit: metadata only (entity types, counts, timings)
```

## Configuration Security

```yaml
# config.yaml — sensitive settings
provider:
  api_key: ""         # Store in PII_PROVIDER_API_KEY env var instead
  endpoint: "http://localhost:1234/v1"  # Local endpoints recommended
```

- API keys for LLM providers can be set via the `PII_PROVIDER_API_KEY` environment variable
- The CLI `--config` flag loads YAML from a local file with no network fetch
- Config version migration (v1 → v2) is handled automatically with no external calls

## Responsible Disclosure

If you discover a security vulnerability, please report it privately:

- **Email:** security@piifilter.dev
- **GitHub:** Create a draft security advisory at github.com/01TEK/piifilter/security/advisories

**Please do not post vulnerabilities publicly until they are resolved.**

We aim to acknowledge reports within 48 hours and provide a fix timeline within 5 business days.

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Regex false positives | Non-PII patterns may be flagged | Tune `confidence_threshold` in config |
| GLiNER detector | Stub — not yet functional | Use regex + Presidio for production |
| Presidio model download | ~400 MB on first use | Download ahead of time; cold start penalty |
| Memory encryption | No encryption of prompt data in memory | Designed for local, trusted environments |
| Rate limiting | Not implemented | Add reverse proxy (nginx) for production |
| Prompt length | Hard truncation at 100 KB | Configurable via `truncate_prompt()` |
| OpenAI Proxy transport | Not yet implemented | Planned for v2.1 |

## Recommended Deployment

### Development
```bash
pip install -e core
piifilter serve
# Access at http://127.0.0.1:8000
```

### Production
```bash
# 1. Use a process manager
systemctl --user start piifilter

# 2. Configure firewall (already bound to localhost by default)
# 3. Review and customize policy rules in config.yaml
# 4. Enable audit logging for compliance tracking
# 5. Run on a dedicated VM or container
```

### Hardening Checklist
- [ ] Port 8000 bound to `127.0.0.1` only (default)
- [ ] No `provider.api_key` stored in config YAML (use env var)
- [ ] Audit logging enabled (`logging.audit_enabled: true`)
- [ ] Policy rules configured for your risk tolerance
- [ ] Unused detectors/strategies removed from [auto-discovery]
- [ ] `confidence_threshold` tuned to reduce false positives
- [ ] Process manager configured for automatic restart
- [ ] Regular `piifilter doctor` checks in monitoring pipeline

## Dependencies & SBOM

PIIFilter v2 has minimal runtime dependencies:
- `pydantic>=2.0.0` — configuration models
- `pyyaml>=6.0` — config file parsing

Optional extras:
- `presidio-analyzer` — NER-based detection (~400 MB)
- `uvicorn` — REST API server
- `mcp>=1.0.0` — MCP server transport
- `click` — CLI framework

All dependencies are pure Python, auditable, and pulled from PyPI. No binary blobs, no telemetry, no analytics.

## Version

This security document applies to PIIFilter **v2.0.0** and later.

---

*Last updated: July 2026*