# HugrGate Go SDK

`github.com/runeforgeai/hugrgate-go` — client for the HugrGate HTTP
service (protocol v1). Slice 431.

## Use

```go
import "github.com/runeforgeai/hugrgate-go"

client, _ := hugrgate.NewClient("http://127.0.0.1:8377")
result, err := client.Decide(ctx,
    map[string]any{"signal": 0.7},
    hugrgate.DecisionSpec{Type: "categorical",
        Options: []string{"a", "b"}},
    nil, nil, nil)
```

## API

- `NewClient(url)` / `NewClientWithOptions(url, Options)`
  (`Timeout`, `MaxRetries`, `RetryBackoff`)
- `Decide(ctx, state, spec, policy, backendName, context)`
- `DecideBatch(ctx, states, spec, policy, backendName)` —
  per-item outcomes, never panics on item failure
- `DecideValue(ctx, state, spec, policy, backendName)`
- `Health(ctx)` — never fails on transport; reports `reachable`
- `Backends(ctx)`, `Protocol(ctx)`, `Close()`

## Semantics

- Every `/decide` request carries `protocol_version: "1.0"` and
  `User-Agent: hugrgate-sdk-go/2.0`.
- Transport errors and HTTP 502/503/504 are retried with
  exponential backoff; caller bugs (`spec_error`) return
  immediately as `*Error` with `Recoverable: false`.
- Service error envelopes map onto `*Error`
  (`Code`/`Message`/`Recoverable`/`Details`); abstentions return
  `*Abstention`; exhausted transport returns `*SDKError`.
- Stdlib only — no third-party dependencies.

## Develop

```bash
go test ./...
```
