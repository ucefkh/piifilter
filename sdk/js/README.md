# PIIFilter JS SDK

Local-first AI privacy gateway — JavaScript/TypeScript SDK.

Connects to the [PIIFilter](https://github.com/nousresearch/privacy-proxy-ai) REST API for prompt scanning, filtering, and forwarding. Does **not** bundle the Python core — it talks to the REST API over HTTP.

## Quick Start

```bash
npm install piifilter
```

Make sure the PIIFilter REST API is running:

```bash
# Start the API server (Python)
piifilter serve
# Or use Docker
docker run -p 8000:8000 ghcr.io/nousresearch/piifilter:latest
```

### Filter a prompt

```typescript
import { PIIFilter } from 'piifilter';

const client = new PIIFilter({ baseUrl: 'http://127.0.0.1:8000' });

const result = await client.filter(
  'My email is user@example.com and my SSN is 123-45-6789.',
  'semantic'
);

console.log(result.filtered);
// "My email is [REDACTED] and my SSN is [REDACTED]."
console.log(result.risk);
// { score: 0.95, level: 'high', detected_count: 2, ... }
```

### Scan only (no filtering)

```typescript
const scan = await client.scan('Call me at 555-0123.');
console.log(scan.entities);
// [{ type: 'PHONE_NUMBER', text: '555-0123', start: 11, end: 19, ... }]
```

### Forward (filter → LLM → return)

```typescript
const fwd = await client.forward(
  'What is my email user@example.com?',
  'semantic',
  'openai',
  'gpt-4o'
);
// The prompt is filtered before reaching the LLM, response is returned as-is.
console.log(fwd.response);
```

### Health check

```typescript
const health = await client.health();
console.log(health.status); // "ok"
```

## API

### `PIIFilter(config?)`

| Option    | Type     | Default              | Description                  |
|-----------|----------|----------------------|------------------------------|
| `baseUrl` | `string` | `http://127.0.0.1:8000` | PIIFilter API base URL       |
| `timeout` | `number` | `30000`              | Request timeout in ms        |

### Methods

- **`filter(prompt, mode?, conversationId?)`** — Filter PII from text
- **`scan(prompt)`** — Scan for PII without filtering
- **`forward(prompt, mode?, provider?, model?, conversationId?)`** — Filter then forward to LLM
- **`health()`** — Check API health

## License

MIT