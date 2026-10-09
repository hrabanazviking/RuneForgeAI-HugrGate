# HugrGate TypeScript SDK

`@runeforgeai/hugrgate` — fetch-based client for the HugrGate HTTP
service (protocol v1). Slice 429.

## Install

```bash
npm install @runeforgeai/hugrgate
```

## Use

```ts
import { HugrGateClient, Abstention } from "@runeforgeai/hugrgate";

const client = new HugrGateClient("http://127.0.0.1:8377");

try {
  const result = await client.decide(
    { signal: 0.7 },
    { type: "categorical", options: ["a", "b"] },
  );
  console.log(result.value, result.probability);
} catch (e) {
  if (e instanceof Abstention) console.log("abstained:", e.reason);
  else throw e;
}
```

## API

- `new HugrGateClient(url?, options?)` — `timeoutMs` (default 10000),
  `maxRetries` (default 3), `retryBackoffMs` (default 100),
  `headers`, `fetchImpl` (override for tests/workers).
- `decide(state, spec, policy?, backendName?, context?)`
- `decideBatch(states, spec, policy?, backendName?)` — per-item
  errors returned in place, never thrown.
- `decideValue(state, spec, policy?, backendName?)`
- `health()` — never throws; `{ reachable: false, error }` when down.
- `backends()`, `models()`, `protocol()`, `close()`.

## Semantics

- Every `/decide` request carries `protocol_version: "1.0"` and a
  versioned `User-Agent: hugrgate-sdk-ts/2.0` header.
- Recoverable failures (network errors, HTTP 502/503/504) are
  retried with exponential backoff; caller bugs (`spec_error`,
  non-recoverable taxonomy errors) raise immediately.
- Service error envelopes map onto `HugrGateError`
  (`code`, `message`, `recoverable`, `details`); abstentions raise
  `Abstention`; exhausted transport raises `SDKError`.

## Develop

```bash
npm install
npm test   # tsc (strict) + node --test against a stub HTTP server
npm run build
```
