# HugrGate Rust SDK

Blocking client for the HugrGate HTTP service (protocol v1). Slice 430.

## Use

```rust
use hugrgate::{Client, DecisionSpec};
use std::collections::HashMap;

let client = Client::new("http://127.0.0.1:8377")?;
let spec = DecisionSpec {
    spec_type: Some("categorical".into()),
    options: Some(vec!["a".into(), "b".into()]),
    ..Default::default()
};
let result = client.decide(HashMap::new(), &spec, None, None, None)?;
println!("{} @ {}", result.value, result.probability);
```

## API

- `Client::new(url)` / `Client::with_options(url, ClientOptions)`
  (`timeout`, `max_retries`, `retry_backoff`)
- `decide(state, spec, policy, backend_name, context)`
- `decide_batch(states, spec, policy, backend_name)` — per-item
  `Result`s, never panics on item failure
- `decide_value(...)` — just the decided value
- `health()` — never fails on transport; reports `reachable`
- `backends()`, `protocol()`

## Semantics

- Every `/decide` request carries `protocol_version: "1.0"` and
  `User-Agent: hugrgate-sdk-rs/2.0`.
- Transport errors and HTTP 502/503/504 are retried with
  exponential backoff; caller bugs (`spec_error`, non-recoverable
  taxonomy errors) surface immediately as `Error::HugrGate`.
- Service error envelopes map onto `HugrGateError`
  (`code`/`message`/`recoverable`/`details`); abstentions become
  `Error::Abstention`; exhausted transport becomes `Error::Sdk`.

## Develop

```bash
cargo test
```
