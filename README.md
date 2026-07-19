<p align="center">
  <h1 align="center">PIIFilter v0.1</h1>
  <p align="center"><em>Local-First AI Privacy Gateway — Early Development</em></p>
</p>

<p align="center">
  <a href="https://github.com/ucefkh/piifilter"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://github.com/ucefkh/piifilter/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ucefkh/piifilter/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://pypi.org/project/piifilter/"><img src="https://img.shields.io/pypi/v/piifilter" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
  <a href="SECURITY.md"><img src="https://img.shields.io/badge/security-policy-yellow" alt="Security Policy"></a>
</p>

---

PIIFilter sits **in front of AI** exactly like Nginx sits in front of web apps. Every prompt passes through a pluggable pipeline — detect, assess risk, enforce policy, replace sensitive content — before reaching the LLM.

```text
Input:   "I want my wife Susan to review the contract for our office at 42 Broadway Avenue, New York."
Output:  "I want my wife Janette to review the contract for our office in a major metropolitan business district."
```

No cloud dependency. No prompt storage. Local execution.

---

## Stability

**PIIFilter is in active development (v0.x).** The API will change based on
real-world feedback. We do not make stability guarantees until v1.0.0.

What's **actually validated**:
- ✅ Core pipeline (detect → risk → policy → replace → audit → forward)
- ✅ Plugin system with 7 interfaces
- ✅ 12 plugins (3 detectors, 6 providers, 3 strategies)
- ✅ 6 transport methods (CLI, REST, Chrome, VSCode, MCP, OpenAI Middleware)
- ✅ 392 tests, fuzz suite, CI pipeline
- ✅ Conversation-scoped aliasing with unfilter endpoint
- ✅ Event-driven architecture with 13 lifecycle events

What's **designed but not validated against real LLM usage**:
- ❌ End-to-end flow against a real LLM in production
- ❌ Streaming response handling and unfilter
- ❌ Detection recall against labeled PII datasets
- ❌ Performance under load (>100 concurrent requests)
- ❌ Unfilter reliability across diverse LLM output patterns
- ❌ Production deployment (Docker, systemd, monitoring)

We're building this in the open. Contributions, bug reports, and feedback
about what breaks in your setup are genuinely appreciated.

---

## Quick Start

```bash
# pip install the core (also available on PyPI)
pip install piifilter

# Or run via Docker
docker run -p 8000:8000 ghcr.io/ucefkh/piifilter:latest

# Or use the npm package (SDK for JS/TS)
npm install @piifilter/sdk

# 2. Run the server (REST API on port 8000)
piifilter serve

# 3. Filter a prompt
piifilter filter "Hi, I'm Susan from Acme Corp. My email is susan@acme.com"

# 4. Or use the SDK programmatically
python -c "
import asyncio
from piifilter_sdk import PIIFilter

async def main():
    async with PIIFilter() as pii:
        result = await pii.filter('My SSN is 123-45-6789')
        print(f'Filtered: {result[\"filtered\"]}')
        print(f'Risk: {result[\"risk\"].level} ({result[\"risk\"].score:.0f}/100)')

asyncio.run(main())
"
```

---

## The "Think Like Linux" Positioning

PIIFilter applies the Unix philosophy to AI privacy:

| Traditional Stack | PIIFilter Analogy |
|---|---|
| Nginx / HAProxy | PIIFilter sits in front, routing/filtering requests |
| WAF (Web Application Firewall) | Detection + Policy engine blocks malicious data |
| Reverse proxy | Intercepts prompts before forwarding to LLMs |
| Logging / Audit | Metadata-only audit trail, no prompt content stored |
| Plugin modules (auth, rate-limit) | Plugin architecture for detectors, strategies, providers |

**PIIFilter is the reverse proxy your prompts need.** It doesn't replace your LLM provider — it guards the gate before them.

---

## Architecture

```
                          ┌─────────────────────────────────────────────────────┐
                          │                   TRANSPORT LAYER                    │
                          │  CLI · REST API · SDK · MCP · Chrome · OpenAI Proxy │
                          └──────────────┬──────────────────────────────────────┘
                                         │
                                         ▼
                    ╔══════════════════════════════════════════════╗
                    ║          PIIFILTER CORE (v2)                ║
                    ╠══════════════════════════════════════════════╣
                    ║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ║
                    ║  │ Session  │  │ Pipeline │  │ EventBus │  ║
                    ║  │(unified  │→ │(stage    │→ │(hooks on │  ║
                    ║  │ data obj)│  │ chain)   │  │ each op) │  ║
                    ║  └──────────┘  └──────────┘  └──────────┘  ║
                    ║                                              ║
                    ║  ┌─────────────────────────────────────────┐ ║
                    ║  │        PluginRegistry                    │ ║
                    ║  │  Detectors · Providers · Strategies ·   │ ║
                    ║  │  Policies · Plugins · Metrics           │ ║
                    ║  │  (discovered via piifilter_* packages)   │ ║
                    ║  └─────────────────────────────────────────┘ ║
                    ╚══════════════════════════════════════════════╝
                                         │
                       Pipeline Stages (all pluggable)
              ┌──────────┬──────────┬──────────┬──────────┬──────────┐
              │   1.     │   2.     │   3.     │   4.     │   5.     │
              │ Detect   │  Risk    │  Policy  │ Replace  │ Forward  │
              │ Regex ·  │ Score    │ BLOCK ·  │ Mask ·   │ OpenAI · │
              │ Presidio │ 0-100    │ REPLACE  │ Semantic │ Anthropic│
              │ GLiNER   │          │ REVIEW   │ General. │ Gemini · │
              │ (plugin) │          │          │ (plugin) │ Ollama · │
              │          │          │          │          │ LMStudio │
              └──────────┴──────────┴──────────┴──────────┴──────────┘
                                         │
                                         ▼
                          GPT · Claude · Gemini · LM Studio · Ollama
                          vLLM · DeepSeek · (any OpenAI-compatible API)
```

### Core Never Knows Which Plugins Exist

The PluginRegistry is the central nervous system. The core pipeline (`FilterPipeline`) never imports a specific detector, provider, or strategy — it asks the registry what's available at runtime. Plugins auto-discover via `piifilter_` package prefix scanning:

```python
# A detector registers itself — core never imports it
async def register_plugin(registry):
    registry.register_detector(RegexDetector())
```

### Session — The Single Unified Data Object

Every pipeline stage reads from and writes to a single `Session` object. No stage calls another stage directly. The EventBus emits `before_*` and `after_*` events for every stage, so plugins observe and react without modifying core:

```python
# Pipeline stages are decoupled via events
await event_bus.emit(PipelineEvent.AFTER_DETECTION, session)
# Any plugin subscribed gets the session — audit, metrics, custom logic
```

---

## Features

### Detection — 24 PII Entity Types

| Category | Entity Types |
|---|---|
| **Identity** | PERSON, EMAIL, PHONE, ADDRESS, CITY, COUNTRY, COMPANY |
| **Financial** | CREDIT_CARD, IBAN, BANK_ACCOUNT, PASSPORT, SOCIAL_SECURITY |
| **Credentials** | API_KEY, JWT, SSH_KEY, DATABASE_URL, PRIVATE_URL |
| **Internal** | PROJECT_NAME, CUSTOMER_NAME, EMPLOYEE_NAME |
| **Technical** | GPS, DOMAIN, IP_ADDRESS, FILE_PATH |

### 4 Replacement Strategies

| Strategy | Description | Example |
|---|---|---|
| **Mask** | Replace with entity-type label | `[EMAIL]` |
| **Semantic** | Replace with realistic, deterministic alias | `"Susan"` → `"Janette"` |
| **Generalize** | Replace with natural-language category | `"a payment method"` |
| **Policy** | Configurable per-entity rules | Custom filtering logic |

### Policy Engine — Declarative Rules

```yaml
policy:
  rules:
    - if: { type: API_KEY }
      action: BLOCK           # Block prompts containing API keys
    - if: { risk: 80, operator: ">" }
      action: BLOCK           # Block prompts with risk score > 80
    - if: { type: PERSON }
      action: REPLACE         # Replace names with aliases
```

### Risk Scoring — 0–100 with Explainability

```text
Input:  "My API key is sk-abc123 and I live in New York"
Score:  30/100  CRITICAL (API_KEY = 25 pts + ADDRESS = 10 pts)
Action: BLOCKED — "Policy BLOCK: API_KEY detected (sk-abc123)"
```

### Deterministic Aliases

Same input always maps to same alias — reversible for audit and debugging:

```text
"Susan"    → "Janette"   (every time)
"Acme Corp" → "Globex Inc"  (every time)
```

---

## Transport Methods

PIIFilter v2 supports **6 transports**, all backed by the same core pipeline:

| Transport | Command / Setup | Use Case |
|---|---|---|
| **CLI** | `piifilter filter "prompt" --mode semantic` | Scripting, manual checks, CI/CD |
| **REST API** | `piifilter serve` (port 8000) | Web apps, integration tests |
| **SDK** | `from piifilter_sdk import PIIFilter` | Python applications |
| **Chrome Extension** | Load unpacked from `apps/chrome-extension/` | ChatGPT, Claude, Gemini, Perplexity |
| **MCP Server** | `mcp run piifilter_mcp.server:server` | Claude Desktop / Claude Code tools |
| **OpenAI Proxy** | Coming in v2.1 — transparent proxy | Any OpenAI-compatible client |

---

## SDK Usage

The SDK is the fastest path to integrate PIIFilter into a Python application:

```python
from piifilter_sdk import PIIFilter

async with PIIFilter() as pii:
    # Filter — detect, risk-assess, replace
    result = await pii.filter("My email is john@example.com")
    print(result["filtered"])   # "My email is [EMAIL REDACTED]"
    print(result["risk"].level) # LOW / MEDIUM / HIGH / CRITICAL

    # Scan — detect only, no replacement
    scan = await pii.scan("Call me at +1 555-123-4567")
    print(f"{scan['count']} entities found")

    # Forward — filter then send to LLM
    response = await pii.forward(
        "What is my email?",
        provider="openai",
        model="gpt-4o"
    )
    print(response["response"])
```

---

## Configuration v2

Declarative YAML with version migration (v1 → v2 automatic):

```yaml
config_version: 2
schema_version: 1

provider:
  name: lmstudio
  endpoint: http://localhost:1234/v1
  api_key: ""                     # Or set PII_PROVIDER_API_KEY env var

detection:
  enabled_detectors:
    - regex
    - presidio
  confidence_threshold: 0.5
  min_votes: 1

replacement:
  default_strategy: semantic      # mask | semantic | generalize
  seed: deterministic

policy:
  rules:
    - if: { type: API_KEY }
      action: BLOCK
    - if: { risk: 80, operator: ">" }
      action: BLOCK

logging:
  level: INFO
  audit_enabled: true
```

---

## Plugin Development Guide

Write a custom detector in ~20 lines:

```python
# mydetector/src/piifilter_detector_mydetector/detector.py
from piifilter.interfaces.detector import Detector
from piifilter.shared.models import DetectedEntity, EntityType

class MyDetector(Detector):
    name = "mydetector"

    async def detect(self, text, *, language=None):
        entities = []
        if "secret" in text.lower():
            entities.append(DetectedEntity(
                entity_type=EntityType.API_KEY,
                value="secret",
                start=text.lower().index("secret"),
                end=text.lower().index("secret") + 6,
                confidence=0.9,
                detector="mydetector",
            ))
        return [{
            "text": e.value, "type": e.type.value,
            "start": e.start, "end": e.end,
            "score": e.score, "detector": e.detector,
        } for e in entities]

    async def initialize(self): pass
    async def shutdown(self): pass
```

```python
# mydetector/src/piifilter_detector_mydetector/__init__.py
async def register_plugin(registry):
    from .detector import MyDetector
    registry.register_detector(MyDetector())
```

Build it, install it, and it's auto-discovered:

```bash
pip install -e plugins/mydetector
piifilter doctor  # "MyDetector" appears in registry
```

### Plugin Types

| Plugin Type | Interface | Purpose |
|---|---|---|
| **Detector** | `piifilter.interfaces.Detector` | PII detection (regex, ML, API) |
| **Provider** | `piifilter.interfaces.Provider` | LLM provider integration |
| **ReplacementStrategy** | `piifilter.interfaces.ReplacementStrategy` | How to replace/modify PII |
| **PolicyEngine** | `piifilter.interfaces.PolicyEngine` | Custom policy rules |
| **Plugin** | `piifilter.interfaces.Plugin` | Lifecycle hooks & aggregator features |
| **MetricsProvider** | `piifilter.interfaces.MetricsProvider` | Counters, histograms, gauges |

---

## CLI Reference

```bash
Commands:
  scan       Detect sensitive entities in a prompt (no modification)
  filter     Detect, risk-assess, replace, and optionally forward
  explain    Detect + risk + detailed explanation per entity
  serve      Start the REST API server
  doctor     Pipeline health check (config, registry, connectivity)
  config     View or initialise configuration
  benchmark  Performance benchmarking (requires optional dependency)

Global options:
  -c, --config PATH   Path to YAML config file
  -v, --verbose       Enable debug logging

Examples:
  piifilter scan "My name is John"
  piifilter filter "Call +1-555-1234" --mode mask
  piifilter filter "What's my email?" --forward
  piifilter explain "My API key is sk-xxx"
  piifilter serve --port 8000
  piifilter doctor
  piifilter config --show
  piifilter config --init ./my-config.yaml
```

---

## Performance

| Metric | Target | Measured |
|---|---|---|
| Detection | <20 ms | ~5 ms (regex) / ~15 ms (presidio) |
| Replacement | <15 ms | ~2 ms |
| Full Pipeline | <50 ms | ~25 ms |
| RAM | <500 MB | ~120 MB (cold) / ~480 MB (presidio loaded) |
| Cold Start | <3 s | ~1.5 s / ~3.5 s (presidio download) |

---

## Project Structure

```
piifilter/
├── core/                        # Core pipeline (no transport code)
│   └── src/piifilter/
│       ├── pipeline/            # Event-driven stage chain
│       ├── interfaces/          # ABCs: Detector, Provider, Strategy, Policy, Plugin
│       ├── registry/            # PluginRegistry + PluginLoader
│       ├── events/              # EventBus + AuditTrailPlugin
│       ├── shared/              # Models (EntityType, Session, RiskAssessment)
│       ├── config.py            # FilterConfig with v1→v2 migration
│       └── session.py           # Single unified data object
│
├── sdk/                         # Python SDK (from piifilter_sdk import PIIFilter)
├── apps/
│   ├── cli/                     # CLI (piifilter scan/filter/explain/serve/doctor/config)
│   ├── rest-api/                # FastAPI REST server
│   ├── chrome-extension/        # Browser extension
│   └── mcp-server/              # MCP server for Claude Desktop
│
├── plugins/
│   ├── detector-regex/          # Regex-based PII detection
│   ├── detector-presidio/       # Microsoft Presidio NER detection
│   ├── detector-gliner/         # GLiNER zero-shot NER (stub)
│   ├── strategy-semantic/       # Semantic alias replacement
│   ├── strategy-mask/           # [ENTITY_TYPE] masking
│   ├── strategy-generalize/     # Natural-language category labels
│   ├── provider-openai/         # OpenAI API provider
│   ├── provider-anthropic/      # Anthropic API provider
│   ├── provider-gemini/         # Google Gemini provider
│   ├── provider-ollama/         # Ollama local provider
│   ├── provider-lmstudio/       # LM Studio local provider
│   └── provider-vllm/           # vLLM provider
│
├── tests/
├── benchmarks/
├── SECURITY.md
└── LICENSE
```

---

## Security

See [SECURITY.md](SECURITY.md) for the full threat model, attack surface analysis, and hardening checklist.

**Key commitments:**
- ✅ No telemetry or analytics
- ✅ No cloud dependency
- ✅ No prompt storage by default
- ✅ Local execution only
- ✅ Memory wiped after request
- ✅ Open source (MIT)

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the current plan and honest maturity assessment.

---

## Contributing

1. Read [SECURITY.md](SECURITY.md)
2. Fork the repo
3. Add a plugin (detectors, providers, strategies — all follow the same interface pattern)
4. Open a PR

All plugin interfaces are defined in `core/src/piifilter/interfaces/`. Plugins auto-discover via the `piifilter_` package prefix — no core modifications needed.

---

## License

MIT — [01TEK](https://github.com/01TEK)

*PIIFilter is not affiliated with any LLM provider. It is a local privacy tool designed to give you control over what your prompts expose.*