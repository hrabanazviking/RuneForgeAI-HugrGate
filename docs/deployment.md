# Deployment guide

How to run HugrGate as a production service. Platform-specific
packaging lives in its own docs: `deploy/docker/` (slice 446),
`deploy/systemd/` (slice 447), Windows (slice 448), macOS
launchd (slice 449).

## 1. Install

The daemon needs the server extra (FastAPI + uvicorn + httpx):

```bash
pip install 'hugrgate[server]'
```

Verify the install and the environment before you deploy:

```bash
hugrgate doctor          # 4 checks: import, server extra, protocol, loopback
hugrgate --version
```

## 2. Configure

Generate a config file, then edit it — explicit CLI flags always
override the file:

```bash
hugrgate gen daemon --out /etc/hugrgate/hugrgate.yaml
hugrgate serve --config /etc/hugrgate/hugrgate.yaml
```

Key knobs (`hugrgate serve --help` lists them all):

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` / `--port` | `127.0.0.1` / `8377` | bind address |
| `--unix-socket` | — | bind a unix socket instead (same-host IPC) |
| `--batch-window-ms` | `5.0` | batching window for `/decide` |
| `--max-batch` / `--max-queue` | `32` / `1024` | backpressure limits |
| `--client-policies` | — | JSON file mapping `X-Client-Id` → server-side policy |
| `--config` | — | `hugrgate.yaml` config file |

## 3. Run

```bash
hugrgate serve --host 0.0.0.0 --port 8377
```

Health and protocol endpoints for load balancers and monitors:

```bash
curl localhost:8377/health     # {"status": ..., "backends": [...]}
curl localhost:8377/protocol   # negotiated protocol version
```

`GET /protocol` always reports the stable protocol (1.0);
clients that do not send a version are treated as 1.0, so
upgrading the server first is safe (see `docs/migration.md`).

## 4. Harden

- **Bind address:** keep `127.0.0.1` (or a unix socket) unless a
  reverse proxy terminates TLS in front of it. The daemon speaks
  plain HTTP; it does not terminate TLS itself.
- **Client policies:** `--client-policies clients.json` maps an
  `X-Client-Id` header to a server-side `DecisionPolicy`. The
  server-side policy wins over any policy in the request body —
  untrusted clients cannot loosen their own thresholds.
- **Privacy:** `privacy_class="strict"` redacts raw inputs from
  provenance; pick the class per deployment in the policy file.
- **Backpressure:** `--max-queue` bounds memory under load;
  excess requests fail fast with `QueueFull` (recoverable —
  SDK v2 retries) instead of piling up.

## 5. Observe

- `hugrgate doctor --url http://host:8377` probes a live daemon
  (protocol handshake, loopback decide).
- Every `/decide` response carries provenance: backend used,
  latency, calibration profile, fallback flags.
- SDK v2 sends `User-Agent: hugrgate-sdk-py/2.0` — watch it in
  access logs to track client rollout skew.

## 6. Scale

One daemon process serves one uvicorn server; batching
(`--batch-window-ms`, `--max-batch`) amortizes backend cost.
Scale horizontally behind a load balancer — backends are
stateless with respect to the service, and `/health` is safe
for readiness probes. For multi-node deployments see the
cluster docs (`/cluster/*` routes, slice 207).

## 7. Upgrade

1. Deploy the new server; old clients keep working (protocol
   negotiation).
2. Migrate contract dicts with `hugrgate.compat.migrate_contract`
   and review the migration report.
3. Roll SDK v2 clients; confirm via the `User-Agent` in logs.

Full detail: `docs/migration.md`.
