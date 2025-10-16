// Auto-generated client. Do not edit by hand.
import { z } from 'zod';

const BASELINE_HASH = '41fd324abc2eb1eea34fca30e00133fd0114cd46bd5dcee1878e71d9c2f5094b';

export interface ClientOptions { baseUrl: string; apiKey?: string; fetchImpl?: typeof fetch; spkiPin?: string }

export class ClientError extends Error {
  constructor(readonly status: number, readonly body: unknown) {
    super(`Request failed with status ${status}`);
  }
}

export class FraudApiClient {
  readonly version = '0.0.0';
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly fetchImpl: typeof fetch;
  private readonly spkiPin?: string;
  lastQuotaRemaining?: number;
  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.spkiPin = options.spkiPin;
  }
  private async request(path: string, init: RequestInit): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set('X-API-Baseline-Hash', BASELINE_HASH);
    if (this.apiKey) { headers.set('X-API-Key', this.apiKey); }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
    if (this.spkiPin) {
      const pin = response.headers.get('X-SPKI-Pin');
      if (pin !== this.spkiPin) {
        throw new ClientError(598, { error: 'spki-mismatch' });
      }
    }
    const remaining = response.headers.get('X-RateLimit-Remaining');
    if (remaining) {
      const parsed = Number(remaining);
      if (!Number.isNaN(parsed)) {
        this.lastQuotaRemaining = parsed;
      }
    }
    if (!response.ok) {
      let body: unknown;
      try { body = await response.json(); } catch { body = await response.text(); }
      throw new ClientError(response.status, body);
    }
    return response;
  }
}
