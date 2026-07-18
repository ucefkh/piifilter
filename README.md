# PIIFilter — Local-First AI Privacy Gateway

Detect, classify, and semantically replace sensitive information before prompts reach LLMs.

```
Input:   "I want my wife Susan to review the contract for our office at 42 Broadway Avenue, New York."
Output:  "I want my wife Janette to review the contract for our office in a major metropolitan business district."
```

No cloud dependency. No prompt storage. Local execution. <50ms latency.

## Quick Start

```bash
# Install
cd packages/core
pip install -e .

# Run the server
piifilter serve

# With config
piifilter serve -c config.yaml

# Scan a prompt for PII
piifilter scan "Hi, I'm Susan from Acme Corp. My email is susan@acme.com"

# Filter a prompt
piifilter filter "Call me at +1 555-123-4567" --mode semantic

# Filter and forward to LLM
piifilter filter "My API key is sk-abc123" --forward

# Run diagnostics
piifilter doctor

# Benchmark performance
piifilter benchmark -n 200

# View configuration
piifilter config
```

## Architecture

```
User
  │
  ├── Chrome Extension
  ├── REST API (FastAPI)
  └── CLI
       │
       ▼
  ╔══════════════════╗
  ║    PIIFilter     ║
  ╠══════════════════╣
  ║ Detection Engine ║  ← Regex + Presidio + GLiNER
  ║ Risk Engine      ║  ← 0-100 scoring
  ║ Replacement Eng. ║  ← Mask / Semantic / Generalize / Policy
  ║ LLM Gateway      ║  ← OpenAI, Anthropic, Gemini, LM Studio, Ollama
  ╚══════════════════╝
       │
       ▼
  GPT · Claude · Gemini · LM Studio · Ollama · vLLM · DeepSeek
```

## Features

- **24 PII entity types**: PERSON, EMAIL, PHONE, ADDRESS, API_KEY, JWT, CREDIT_CARD, IBAN, SSH_KEY, DATABASE_URL, GPS, and more
- **4 replacement modes**: Mask, Semantic (realistic aliases), Generalize (category-level), Policy (configurable)
- **Deterministic aliases**: Same input always maps to same alias
- **Risk scoring**: 0-100 with LOW/MEDIUM/HIGH/CRITICAL levels
- **LLM Gateway**: Forward sanitized prompts to 7+ providers
- **Chrome Extension**: Intercepts prompts before submission
- **Zero storage**: No prompt data persisted by default
- **<50ms latency**: Optimized for real-time use

## Configuration

Edit `config.yaml`:

```yaml
replacement_mode: semantic    # mask | semantic | generalize | policy
risk_threshold: medium        # low | medium | high | critical
store_logs: false             # never store prompts
replacement_seed: deterministic
provider:
  name: lmstudio              # lmstudio | ollama | openai | anthropic | gemini | vllm | deepseek
  endpoint: http://localhost:1234/v1
  api_key: ""
  default_model: gpt-3.5-turbo
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/filter` | POST | Detect and replace PII |
| `/scan` | POST | Scan for PII without modifying |
| `/risk` | POST | Assess risk score only |
| `/health` | GET | Health check |
| `/config` | POST | Get current configuration |
| `/forward` | POST | Filter + forward to LLM |

## Chrome Extension

1. Build the extension (load unpacked from `apps/chrome-extension/`)
2. Start PIIFilter server: `piifilter serve`
3. Prompts on ChatGPT, Claude, Gemini, and Perplexity are intercepted and filtered

## Performance Targets

| Metric | Target |
|--------|--------|
| Detection | <20ms |
| Replacement | <15ms |
| Total | <50ms |
| RAM | <500MB |
| Cold Start | <3s |

## Security

- ✅ No telemetry
- ✅ No analytics
- ✅ No cloud dependency
- ✅ No prompt storage
- ✅ Local execution only
- ✅ Memory wiped after request
- ✅ Open source

## Roadmap (Post-MVP)

- Custom lightweight anonymization model
- OCR for PDFs and images
- Voice transcription filtering
- IDE plugins (VS Code, JetBrains)
- Slack, Teams, Discord integrations
- Enterprise policy engine
- MCP server integration

## License

MIT — 01TEK