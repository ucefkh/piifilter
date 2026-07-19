import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PIIFilter } from './client';
import type { Mock } from 'vitest';

const createMockFetch = () => {
  const mockFetch = vi.fn() as unknown as Mock;
  globalThis.fetch = mockFetch;
  return mockFetch;
};

const mockJsonResponse = (data: unknown, status = 200) => {
  const mock = createMockFetch();
  mock.mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(status >= 200 && status < 300 ? '' : JSON.stringify(data)),
    json: () => Promise.resolve(data),
  });
  return mock;
};

describe('PIIFilter', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('constructor', () => {
    it('uses default baseUrl when no config provided', () => {
      const client = new PIIFilter();
      expect(client).toBeInstanceOf(PIIFilter);
    });

    it('accepts custom baseUrl', () => {
      const client = new PIIFilter({ baseUrl: 'http://localhost:8080' });
      expect(client).toBeInstanceOf(PIIFilter);
    });

    it('accepts custom timeout', () => {
      const client = new PIIFilter({ timeout: 5000 });
      expect(client).toBeInstanceOf(PIIFilter);
    });
  });

  describe('filter', () => {
    it('sends POST to /v1/filter and returns FilterResult', async () => {
      const mockData = {
        filtered: 'My email is [REDACTED].',
        risk: {
          score: 0.85,
          level: 'high',
          detected_count: 1,
          critical_entities: ['EMAIL'],
          recommendation: 'Review and sanitize',
        },
        entities: [{ type: 'EMAIL', text: 'user@example.com', start: 12, end: 26, score: 0.99, detector: 'regex' }],
        replacements: [{ original: 'user@example.com', replacement: '[REDACTED]', entity_type: 'EMAIL' }],
        latency_ms: 42,
        blocked: false,
      };
      mockJsonResponse(mockData);

      const client = new PIIFilter();
      const result = await client.filter('My email is user@example.com.', 'semantic');

      expect(result).toEqual(mockData);
      expect(fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/v1/filter',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: 'My email is user@example.com.', mode: 'semantic' }),
        })
      );
    });

    it('passes conversationId when provided', async () => {
      mockJsonResponse({ filtered: '', risk: { score: 0, level: 'low', detected_count: 0, critical_entities: [], recommendation: '' }, entities: [], replacements: [], latency_ms: 0, blocked: false });

      const client = new PIIFilter();
      await client.filter('Hi', 'semantic', 'conv-123');

      const body = JSON.parse((fetch as Mock).mock.calls[0][1].body);
      expect(body.conversation_id).toBe('conv-123');
    });
  });

  describe('scan', () => {
    it('sends POST to /v1/scan and returns ScanResult', async () => {
      const mockData = {
        entities: [{ type: 'PHONE', text: '555-0123', start: 11, end: 19, score: 0.95, detector: 'regex' }],
        risk: { score: 0.5, level: 'medium', detected_count: 1, critical_entities: [], recommendation: 'Review' },
        latency_ms: 15,
      };
      mockJsonResponse(mockData);

      const client = new PIIFilter();
      const result = await client.scan('Call me at 555-0123.');

      expect(result).toEqual(mockData);
      expect(fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/v1/scan',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  describe('forward', () => {
    it('sends POST to /v1/forward and returns ForwardResult', async () => {
      const mockData = {
        filtered: 'What is my email [REDACTED]?',
        response: 'Your email is on file.',
        risk: { score: 0.7, level: 'medium', detected_count: 1, critical_entities: [], recommendation: 'Review' },
        entities: [{ type: 'EMAIL', text: 'user@example.com', start: 18, end: 32, score: 0.99, detector: 'regex' }],
        latency_ms: 123,
      };
      mockJsonResponse(mockData);

      const client = new PIIFilter();
      const result = await client.forward('What is my email user@example.com?', 'semantic', 'openai', 'gpt-4o');

      expect(result).toEqual(mockData);
      const body = JSON.parse((fetch as Mock).mock.calls[0][1].body);
      expect(body.provider).toBe('openai');
      expect(body.model).toBe('gpt-4o');
    });
  });

  describe('health', () => {
    it('sends GET to /v1/health', async () => {
      mockJsonResponse({ status: 'ok' });

      const client = new PIIFilter();
      const result = await client.health();

      expect(result).toEqual({ status: 'ok' });
      expect(fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/v1/health',
        expect.objectContaining({ method: 'GET' })
      );
    });
  });

  describe('error handling', () => {
    it('throws on non-ok response', async () => {
      const mock = createMockFetch();
      mock.mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error'),
      });

      const client = new PIIFilter();
      await expect(client.health()).rejects.toThrow('PIIFilter API error (500): Internal Server Error');
    });

    it('throws on network error', async () => {
      const mock = createMockFetch();
      mock.mockRejectedValue(new Error('Network error'));

      const client = new PIIFilter();
      await expect(client.health()).rejects.toThrow('Network error');
    });

    it('respects timeout', async () => {
      const mock = createMockFetch();
      mock.mockImplementation(() => new Promise((_, reject) => {
        setTimeout(() => reject(new Error('AbortError')), 500);
      }));

      const client = new PIIFilter({ timeout: 10 });
      await expect(client.health()).rejects.toThrow();
    });
  });
});