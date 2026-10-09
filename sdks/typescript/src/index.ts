/**
 * HugrGate TypeScript SDK — slice 429.
 *
 * fetch-based client for the HugrGate HTTP service (protocol v1):
 * versioned requests, taxonomy error mapping, exponential-backoff
 * retry on recoverable faults, and batch decisions.
 *
 * Usage:
 *   import { HugrGateClient } from "@runeforgeai/hugrgate";
 *   const client = new HugrGateClient("http://127.0.0.1:8377");
 *   const result = await client.decide({ signal: 0.7 },
 *     { type: "categorical", options: ["a", "b"] });
 */

export const PROTOCOL_VERSION = "1.0";
export const SDK_VERSION = "2.0";

/** DecisionSpec JSON (see hugrgate.spec). */
export interface DecisionSpec {
  type?: string;
  options?: string[];
  statement?: string;
  levels?: string[];
  minimum?: number;
  maximum?: number;
  labels?: string[];
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

/** DecisionPolicy JSON (see hugrgate.policy / hugrgate.serde). */
export type DecisionPolicy = Record<string, unknown>;

/** DecisionResult JSON (see hugrgate.result). */
export interface DecisionResult {
  value: unknown;
  probability: number;
  distribution: Record<string, number>;
  uncertainty: number;
  accepted: boolean;
  backend: string;
  model: string;
  latency_ms: number;
  calibration_profile: string;
  fallback_used: boolean;
  metadata: Record<string, unknown>;
}

export interface BackendInfo {
  name: string;
  is_remote: boolean;
  capabilities: Record<string, unknown>;
  estimated_latency_ms?: number;
  estimated_cost?: number;
  calibration?: Record<string, unknown>;
  privacy?: Record<string, unknown>;
  health?: Record<string, unknown>;
}

export interface ProtocolInfo {
  protocol_version: string;
  supported_versions: string[];
  service_version: string;
}

/** Wire error envelope: `{ error: { code, message, recoverable, details } }`. */
export interface ErrorEnvelope {
  code: string;
  message: string;
  recoverable: boolean;
  details: Record<string, unknown>;
}

/** A HugrGate taxonomy error raised from a service error envelope. */
export class HugrGateError extends Error {
  readonly code: string;
  readonly recoverable: boolean;
  readonly details: Record<string, unknown>;

  constructor(code: string, message: string, recoverable = true,
              details: Record<string, unknown> = {}) {
    super(`[${code}] ${message}`);
    this.name = "HugrGateError";
    this.code = code;
    this.recoverable = recoverable;
    this.details = details;
  }

  static fromEnvelope(env: ErrorEnvelope): HugrGateError {
    return new HugrGateError(env.code, env.message, env.recoverable,
                             env.details ?? {});
  }
}

/** Raised when the service abstains instead of deciding. */
export class Abstention extends HugrGateError {
  readonly reason: string;

  constructor(message: string, reason: string) {
    super("abstention", message, true, { reason });
    this.name = "Abstention";
    this.reason = reason;
  }
}

/** Raised when the transport fails and no fallback is configured. */
export class SDKError extends HugrGateError {
  constructor(message: string) {
    super("sdk_error", message, true, {});
    this.name = "SDKError";
  }
}

export interface ClientOptions {
  timeoutMs?: number;
  maxRetries?: number;
  retryBackoffMs?: number;
  /** Extra headers merged into every request. */
  headers?: Record<string, string>;
  /** fetch implementation override (tests, undici, workers). */
  fetchImpl?: typeof fetch;
}

const RETRYABLE_STATUS = new Set([502, 503, 504]);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Client for a HugrGate service (protocol v1).
 *
 * Recoverable failures (network errors, HTTP 502/503/504, taxonomy
 * errors flagged recoverable) are retried with exponential backoff;
 * caller bugs (e.g. `spec_error`) are raised immediately.
 */
export class HugrGateClient {
  readonly url: string;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly retryBackoffMs: number;
  private readonly headers: Record<string, string>;
  private readonly fetchImpl: typeof fetch;

  constructor(url = "http://127.0.0.1:8377", options: ClientOptions = {}) {
    if (options.maxRetries !== undefined && options.maxRetries < 0) {
      throw new Error("maxRetries must be >= 0");
    }
    this.url = url.replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 10000;
    this.maxRetries = options.maxRetries ?? 3;
    this.retryBackoffMs = options.retryBackoffMs ?? 100;
    this.headers = {
      "content-type": "application/json",
      "user-agent": `hugrgate-sdk-ts/${SDK_VERSION}`,
      ...(options.headers ?? {}),
    };
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let attempt = 0;
    for (;;) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        const res = await this.fetchImpl(`${this.url}${path}`, {
          ...init,
          headers: this.headers,
          signal: controller.signal,
        });
        clearTimeout(timer);
        if (!res.ok) {
          const mapped = await this.mapError(res);
          if (mapped.recoverable && RETRYABLE_STATUS.has(res.status) &&
              attempt < this.maxRetries) {
            await sleep(this.retryBackoffMs * 2 ** attempt);
            attempt += 1;
            continue;
          }
          throw mapped;
        }
        return (await res.json()) as T;
      } catch (err) {
        clearTimeout(timer);
        if (err instanceof HugrGateError || err instanceof Abstention) {
          throw err;
        }
        // Network-level failure: retry, then give up as SDKError.
        if (attempt < this.maxRetries) {
          await sleep(this.retryBackoffMs * 2 ** attempt);
          attempt += 1;
          continue;
        }
        throw new SDKError(
          `hugrgate service unreachable: ${(err as Error).message ?? err}`);
      }
    }
  }

  private async mapError(res: Response): Promise<HugrGateError> {
    let envelope: ErrorEnvelope | null = null;
    try {
      const body = (await res.json()) as { error?: ErrorEnvelope };
      if (body && body.error && typeof body.error.code === "string") {
        envelope = body.error;
      }
    } catch {
      envelope = null; // unparseable body: generic mapping below
    }
    if (envelope) return HugrGateError.fromEnvelope(envelope);
    if (res.status === 422) {
      return new HugrGateError("spec_error",
        `service rejected request (HTTP 422)`, false, {});
    }
    if (res.status === 503) {
      return new HugrGateError("backend_unavailable",
        "service unavailable (HTTP 503)", true, {});
    }
    return new HugrGateError("backend_error",
      `service error (HTTP ${res.status})`, true, {});
  }

  /** Make a decision via the service. */
  async decide(state: Record<string, unknown>,
               spec: DecisionSpec,
               policy?: DecisionPolicy,
               backendName?: string,
               context?: Record<string, unknown>): Promise<DecisionResult> {
    const payload: Record<string, unknown> = {
      protocol_version: PROTOCOL_VERSION,
      spec,
      state,
      backend_name: backendName ?? null,
      context: context ?? null,
    };
    if (policy !== undefined) payload["policy"] = policy;
    const body = await this.request<Record<string, unknown>>("/decide", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (body["abstained"]) {
      throw new Abstention(
        (body["message"] as string) || "service abstained",
        (body["reason"] as string) || "below_threshold");
    }
    const decision = (body["decision"] ?? body) as Record<string, unknown>;
    if (typeof decision !== "object" || decision === null ||
        !("value" in decision)) {
      throw new SDKError(
        `service returned no decision: ${JSON.stringify(body)}`);
    }
    const result = decision as unknown as DecisionResult;
    result.metadata = result.metadata ?? {};
    result.metadata["client_transport"] = "http";
    result.metadata["sdk_version"] = SDK_VERSION;
    return result;
  }

  /** Decide one spec over many states; per-item errors are returned. */
  async decideBatch(states: Record<string, unknown>[],
                    spec: DecisionSpec,
                    policy?: DecisionPolicy,
                    backendName?: string,
  ): Promise<Array<DecisionResult | HugrGateError>> {
    const outcomes: Array<DecisionResult | HugrGateError> = [];
    for (const state of states) {
      try {
        outcomes.push(await this.decide(state, spec, policy, backendName));
      } catch (err) {
        outcomes.push(err instanceof HugrGateError
          ? err : new SDKError(String(err)));
      }
    }
    return outcomes;
  }

  /** Convenience: just the decided value. */
  async decideValue(state: Record<string, unknown>,
                    spec: DecisionSpec,
                    policy?: DecisionPolicy,
                    backendName?: string): Promise<unknown> {
    return (await this.decide(state, spec, policy, backendName)).value;
  }

  /** Liveness probe. Never throws: reports reachability. */
  async health(): Promise<Record<string, unknown> & { reachable: boolean }> {
    try {
      const data = await this.request<Record<string, unknown>>("/health");
      return { ...data, reachable: true };
    } catch (err) {
      return { reachable: false, error: String(err) };
    }
  }

  /** List backends known to the service. */
  async backends(): Promise<BackendInfo[]> {
    return this.request<BackendInfo[]>("/backends");
  }

  /** List known models. */
  async models(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("/models");
  }

  /** Fetch the service's protocol advertisement. */
  async protocol(): Promise<ProtocolInfo> {
    return this.request<ProtocolInfo>("/protocol");
  }

  /** Release resources (no-op for fetch; kept for API symmetry). */
  close(): void {
    // fetch has no persistent handles to release.
  }
}
