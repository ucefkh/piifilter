import { PIIFilterConfig, FilterResult, ScanResult, ForwardResult } from './types';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000';

export class PIIFilter {
  private baseUrl: string;
  private timeout: number;

  constructor(config: PIIFilterConfig = {}) {
    this.baseUrl = config.baseUrl || DEFAULT_BASE_URL;
    this.timeout = config.timeout || 30000;
  }

  async filter(prompt: string, mode: string = 'semantic', conversationId?: string): Promise<FilterResult> {
    const res = await this._fetch('/v1/filter', { prompt, mode, conversation_id: conversationId });
    return res;
  }

  async scan(prompt: string): Promise<ScanResult> {
    const res = await this._fetch('/v1/scan', { prompt });
    return res;
  }

  async forward(prompt: string, mode: string = 'semantic', provider?: string, model?: string, conversationId?: string): Promise<ForwardResult> {
    const res = await this._fetch('/v1/forward', { prompt, mode, provider, model, conversation_id: conversationId });
    return res;
  }

  async health(): Promise<{ status: string }> {
    const res = await this._fetch('/v1/health');
    return res;
  }

  private async _fetch(path: string, body?: unknown): Promise<any> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeout);

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method: body ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`PIIFilter API error (${res.status}): ${errorText}`);
      }

      return await res.json();
    } finally {
      clearTimeout(timeout);
    }
  }
}