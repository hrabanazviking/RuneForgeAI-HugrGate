/**
 * TypeScript SDK tests — slice 429.
 *
 * Run: `npm test` (compiles with tsc, then node --test).
 * A stub HTTP server plays scripted responses so the tests exercise
 * retry, error mapping, batching, and the protocol advertisement
 * without a real HugrGate service.
 */
import { strict as assert } from "node:assert";
import { createServer, type Server } from "node:http";
import { describe, it, before, after } from "node:test";
import {
  Abstention,
  HugrGateClient,
  HugrGateError,
  PROTOCOL_VERSION,
  SDK_VERSION,
  SDKError,
} from "./index.js";

const SPEC = { type: "categorical", options: ["a", "b"] };

function okBody() {
  return {
    value: "a",
    probability: 1.0,
    distribution: { a: 1.0 },
    uncertainty: 0.0,
    accepted: true,
    backend: "stub",
    model: "stub-1",
    latency_ms: 0.1,
    calibration_profile: "none",
    fallback_used: false,
    metadata: {},
  };
}

function errBody(code: string, recoverable: boolean) {
  return {
    error: { code, message: `${code} happened`, recoverable, details: {} },
  };
}

type Scripted = Array<
  | { status: number; body: unknown }
  | { hang: true }
  | { badJson: true; status?: number }
>;

let server: Server;
let script: Scripted = [];
let requests: Array<{ url: string; body: unknown; headers: unknown }> = [];

function enqueue(...items: Scripted) {
  script.push(...items);
}

before(async () => {
  server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      requests.push({
        url: req.url ?? "",
        body: raw ? JSON.parse(raw) : null,
        headers: req.headers,
      });
      const next = script.shift();
      if (!next || "hang" in next) {
        return; // hang: never respond -> client timeout
      }
      if ("badJson" in next) {
        res.writeHead(next.status ?? 200, {
          "content-type": "application/json",
        });
        res.end("this is not json{{{");
        return;
      }
      res.writeHead(next.status, { "content-type": "application/json" });
      res.end(JSON.stringify(next.body));
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
});

after(async () => {
  await new Promise<void>((r) => server.close(() => r()));
});

function port(): number {
  const addr = server.address();
  if (typeof addr === "object" && addr) return addr.port;
  throw new Error("server not listening");
}

function client(opts: Record<string, unknown> = {}) {
  return new HugrGateClient(`http://127.0.0.1:${port()}`, {
    retryBackoffMs: 0,
    timeoutMs: 2000,
    ...opts,
  } as never);
}

describe("protocol", () => {
  it("sends protocol_version on decide", async () => {
    requests = [];
    enqueue({ status: 200, body: okBody() });
    const c = client();
    await c.decide({ f: 1 }, SPEC);
    const first = requests[0];
    assert.ok(first);
    assert.equal(first.url, "/decide");
    assert.equal(
      (first.body as Record<string, unknown>)["protocol_version"],
      PROTOCOL_VERSION,
    );
  });

  it("sends a versioned user-agent", async () => {
    requests = [];
    enqueue({ status: 200, body: okBody() });
    const c = client();
    await c.decide({ f: 1 }, SPEC);
    const first = requests[0];
    assert.ok(first);
    const headers = first.headers as Record<string, string>;
    assert.equal(headers["user-agent"], `hugrgate-sdk-ts/${SDK_VERSION}`);
  });

  it("fetches the protocol advertisement", async () => {
    enqueue({
      status: 200,
      body: {
        protocol_version: "1.0",
        supported_versions: ["1.0"],
        service_version: "0.1.0",
      },
    });
    const c = client();
    const info = await c.protocol();
    assert.equal(info.protocol_version, "1.0");
    assert.deepEqual(info.supported_versions, ["1.0"]);
  });
});

describe("decide", () => {
  it("returns the decision and stamps metadata", async () => {
    enqueue({ status: 200, body: okBody() });
    const c = client();
    const result = await c.decide({ f: 1 }, SPEC);
    assert.equal(result.value, "a");
    assert.equal(result.metadata["sdk_version"], SDK_VERSION);
    assert.equal(result.metadata["client_transport"], "http");
  });

  it("raises Abstention on abstain envelopes", async () => {
    enqueue({
      status: 200,
      body: { abstained: true, reason: "below_threshold", message: "low" },
    });
    const c = client();
    await assert.rejects(() => c.decide({ f: 1 }, SPEC), (e: unknown) => {
      assert.ok(e instanceof Abstention);
      assert.equal((e as Abstention).reason, "below_threshold");
      return true;
    });
  });

  it("maps 422 envelopes to taxonomy errors without retry", async () => {
    enqueue({ status: 422, body: errBody("spec_error", false) });
    const c = client({ maxRetries: 3 });
    const start = Date.now();
    await assert.rejects(() => c.decide({ f: 1 }, SPEC), (e: unknown) => {
      assert.ok(e instanceof HugrGateError);
      assert.equal((e as HugrGateError).code, "spec_error");
      assert.equal((e as HugrGateError).recoverable, false);
      return true;
    });
    assert.equal(requests.filter((r) => r.url === "/decide").length >= 1, true);
    assert.ok(Date.now() - start < 1500, "caller bugs must not be retried");
  });

  it("retries 503 then succeeds", async () => {
    requests = [];
    enqueue(
      { status: 503, body: errBody("backend_unavailable", true) },
      { status: 200, body: okBody() },
    );
    const c = client({ maxRetries: 2 });
    const result = await c.decide({ f: 1 }, SPEC);
    assert.equal(result.value, "a");
    assert.equal(
      requests.filter((r) => r.url === "/decide").length,
      2,
    );
  });

  it("gives up as SDKError when the service hangs", async () => {
    enqueue({ hang: true }, { hang: true }, { hang: true });
    const c = client({ maxRetries: 1, timeoutMs: 50 });
    await assert.rejects(() => c.decide({ f: 1 }, SPEC), (e: unknown) => {
      assert.ok(e instanceof SDKError);
      return true;
    });
  });

  it("rejects negative maxRetries", () => {
    assert.throws(() => client({ maxRetries: -1 }), /maxRetries/);
  });
});

describe("batch", () => {
  it("reports per-item errors in place", async () => {
    enqueue(
      { status: 200, body: okBody() },
      { status: 422, body: errBody("spec_error", false) },
    );
    const c = client();
    const outcomes = await c.decideBatch([{ f: 1 }, { f: 2 }], SPEC);
    assert.equal(outcomes.length, 2);
    assert.equal((outcomes[0] as { value: unknown }).value, "a");
    assert.ok(outcomes[1] instanceof HugrGateError);
  });

  it("decideValue returns just the value", async () => {
    enqueue({ status: 200, body: okBody() });
    const c = client();
    assert.equal(await c.decideValue({ f: 1 }, SPEC), "a");
  });
});

describe("introspection", () => {
  it("health reports reachability", async () => {
    enqueue({ status: 200, body: { status: "ok", version: "0.1.0" } });
    const c = client();
    const h = await c.health();
    assert.equal(h["reachable"], true);
    assert.equal(h["status"], "ok");
  });

  it("health never throws", async () => {
    const c = new HugrGateClient("http://127.0.0.1:1", {
      timeoutMs: 50,
      maxRetries: 0,
    } as never);
    const h = await c.health();
    assert.equal(h["reachable"], false);
  });

  it("backends lists backend infos", async () => {
    enqueue({
      status: 200,
      body: [{ name: "uniform", is_remote: false, capabilities: {} }],
    });
    const c = client();
    const infos = await c.backends();
    const first = infos[0];
    assert.ok(first);
    assert.equal(first.name, "uniform");
  });

  it("close is safe to call", () => {
    const c = client();
    c.close();
  });
});
