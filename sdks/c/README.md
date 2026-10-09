# HugrGate C SDK

Stable C ABI (`include/hugrgate.h`, slice 432) plus a prototype
client implementation (`src/hugrgate.c`, slice 433).

## Layout

- `include/hugrgate.h` — the binary-stability contract. Read the
  six ABI rules at the top before touching anything.
- `src/hugrgate.c` — POSIX-sockets HTTP/1.1 implementation with a
  minimal JSON parser/serializer. C99, no third-party dependencies.
- `e2e/smoke.c` — test driver used by the pytest suite.

## Build

```bash
make        # builds ./smoke
make check  # points at the pytest suite
```

## Prototype limits

- `http://` only — no TLS; `https://` URLs are rejected with
  `HG_ERR_INVALID_ARG`.
- One request per TCP connection (`Connection: close`).
- A client handle is not thread-safe for concurrent `decide()`
  calls; use one handle per thread.
- Retries are the caller's job: `hg_status_recoverable()` tells
  you which statuses are worth retrying.

## Use

```c
#include <hugrgate.h>

hg_client_t *client;
hg_error_t *err = NULL;
if (hg_client_new("http://127.0.0.1:8377", 5000, &client, &err) != HG_OK) {
    fprintf(stderr, "connect: %s\n", err->message);
    hg_error_free(err);
    return 1;
}

hg_decision_t *d = NULL;
hg_status_t st = hg_client_decide(client,
    "{\"type\":\"categorical\",\"options\":[\"a\",\"b\"]}",
    "{\"signal\":0.7}", NULL, NULL, &d, &err);
if (st == HG_OK) {
    printf("value=%s p=%f\n", d->value_json, d->probability);
    hg_decision_free(d);
} else if (st == HG_ERR_ABSTAINED) {
    printf("abstained: %s\n", err->message);
    hg_error_free(err);
} else {
    fprintf(stderr, "[%d] %s (recoverable=%d)\n",
            st, err->message, err->recoverable);
    hg_error_free(err);
}
hg_client_free(client);
```
