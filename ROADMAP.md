# PIIFilter Roadmap

## Current Status: Pre-release (v0.1.0)

PIIFilter is in active development. The architecture is solid but the product
has not been validated against real LLM usage.

## Completed

- [x] Core pipeline (detect → risk → policy → replace → audit → forward)
- [x] Plugin system with 7 interfaces (Detector, Provider, Strategy, Policy, etc)
- [x] 12 plugins (3 detectors, 6 providers, 3 strategies)
- [x] 6 transport methods (CLI, REST, Chrome, VSCode, MCP, OpenAI Middleware)
- [x] Conversation-scoped aliasing with unfilter endpoint
- [x] 392 tests, fuzz suite, CI pipeline
- [x] Event-driven architecture with 13 lifecycle events
- [x] Docker + Docker Compose
- [x] npm TypeScript SDK

## Validated

- [ ] End-to-end flow against a real LLM
- [ ] Streaming response handling and unfilter
- [ ] Detection recall against labeled PII data
- [ ] Performance under load (>100 concurrent requests)
- [ ] Unfilter reliability across diverse LLM output patterns
- [ ] Production deployment (Docker, systemd, monitoring)

## Next Quarter

- [ ] Real provider implementation (Ollama, LM Studio)
- [ ] Streaming pipeline (SSE endpoints, token-boundary alias handling)
- [ ] Persistent AliasStore (SQLite backend with encryption)
- [ ] Detection recall benchmarks with published F1 scores
- [ ] Rate limiting and basic auth for REST API
- [ ] Published Chrome Extension
- [ ] Published PyPI and npm packages