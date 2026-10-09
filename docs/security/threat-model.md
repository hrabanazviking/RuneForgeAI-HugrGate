# Threat model v2

Generated from `hugrgate.security.threat_model.default_threat_model()` (slice 401).
Do not hand-edit the tables — regenerate from the module.

## Trust boundaries

| Boundary | Enforced by |
|---|---|
| `process` | OS user separation; no HugrGate sandbox by default |
| `service_edge` | input validation, size limits, authn/authz |
| `cluster_net` | mutual HMAC auth (slice 208), TLS via operator |
| `model_ingest` | checksum + signature enforcement (slices 405-406) |
| `plugin_loader` | plugin trust model (slice 407), sandbox (slice 408) |

## Threats

| ID | STRIDE | Asset | Risk | Residual | Title |
|---|---|---|---|---|---|
| T-07 | information_disclosure | `secrets` | 20 | partial | Secrets leak into logs, errors, or telemetry |
| T-03 | elevation_of_privilege | `decision_inputs` | 16 | partial | Prompt injection steers an LLM backend |
| T-04 | denial_of_service | `service_api` | 16 | partial | Oversized input exhausts memory/CPU |
| T-01 | elevation_of_privilege | `model_artifacts` | 15 | partial | Malicious model file executes code on load |
| T-02 | tampering | `model_artifacts` | 12 | partial | Tampered model metadata misroutes decisions |
| T-05 | tampering | `decision_cache` | 12 | partial | Cache poisoning serves attacker-chosen decisions |
| T-10 | tampering | `model_artifacts` | 12 | partial | Path traversal in pack/model file loading |
| T-11 | elevation_of_privilege | `plugin_code` | 12 | partial | Malicious backend exfiltrates or hangs |
| T-12 | spoofing | `service_api` | 12 | partial | Unauthenticated service access |
| T-13 | denial_of_service | `service_api` | 12 | partial | Credential-less rate exhaustion (DoS) |
| T-15 | elevation_of_privilege | `plugin_code` | 12 | partial | Untrusted plugin runs with full privileges |
| T-17 | tampering | `model_artifacts` | 12 | partial | Stale/vulnerable transitive dependency |
| T-06 | repudiation | `provenance_chain` | 10 | partial | Provenance chain tampering hides an action |
| T-09 | tampering | `model_artifacts` | 10 | partial | Dependency confusion / compromised package |
| T-14 | spoofing | `provenance_chain` | 9 | partial | Log injection forges audit entries |
| T-16 | denial_of_service | `decision_inputs` | 9 | partial | Fuzz-found crash in parsers/validators |
| T-08 | spoofing | `cluster_traffic` | 8 | partial | Replayed cluster RPC re-executes a decision |
| T-18 | information_disclosure | `decision_cache` | 4 | accepted | Side-channel: timing reveals cache hits |

## Detail

### T-01 — Malicious model file executes code on load

- **STRIDE:** elevation_of_privilege · **Asset:** `model_artifacts` · **Risk:** 3×5=15 · **Residual:** partial
- **Scenario:** A crafted model/pack file triggers code execution via unsafe deserialization or parser bugs during load.
- **Mitigations:**
  - deserialization hardening: SafeUnpickler + opcode scanner (slice 411)
  - checksum enforcement on model files (slice 406)
  - signed model metadata (slice 405)
- **Tests:** `test_sec_406_checksums`, `test_sec_411_serde_guards`

### T-02 — Tampered model metadata misroutes decisions

- **STRIDE:** tampering · **Asset:** `model_artifacts` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** Unsigned metadata edited to change model identity, version, or capability claims; the gate trusts stale/false claims.
- **Mitigations:**
  - HMAC-signed model metadata, verify-before-trust (slice 405)
- **Tests:** `test_sec_405_model_signing`

### T-03 — Prompt injection steers an LLM backend

- **STRIDE:** elevation_of_privilege · **Asset:** `decision_inputs` · **Risk:** 4×4=16 · **Residual:** partial
- **Scenario:** Untrusted tool output or state text contains instructions that an LLM backend obeys over the system prompt.
- **Mitigations:**
  - instruction/data boundary: delimited untrusted content (slice 414)
  - override-attempt detector on backend inputs (slice 414)
- **Tests:** `test_sec_414_prompt_injection`

### T-04 — Oversized input exhausts memory/CPU

- **STRIDE:** denial_of_service · **Asset:** `service_api` · **Risk:** 4×4=16 · **Residual:** partial
- **Scenario:** Giant state payloads, deep nesting, or huge batches cause OOM or CPU starvation before validation completes.
- **Mitigations:**
  - validate_state size/depth caps (slice 011)
  - InputLimits policy with per-key quotas (slice 409)
  - resource budgets: RLIMIT_AS/CPU (slice 410)
- **Tests:** `test_sec_409_input_limits`, `test_sec_410_resource_guards`

### T-05 — Cache poisoning serves attacker-chosen decisions

- **STRIDE:** tampering · **Asset:** `decision_cache` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** Crafted state collides with a victim's cache key, or a stale entry survives a model update and is served as fresh.
- **Mitigations:**
  - cache key binds spec+policy+model version (slice 258 integrity snapshot)
  - tenant namespace isolation (slice 417)
  - model-version invalidation (slice 417)
- **Tests:** `test_sec_417_cache_poisoning`

### T-06 — Provenance chain tampering hides an action

- **STRIDE:** repudiation · **Asset:** `provenance_chain` · **Risk:** 2×5=10 · **Residual:** partial
- **Scenario:** An insider edits or truncates the hash-chained audit log to erase evidence of a decision.
- **Mitigations:**
  - hash-chained records, verify_chain (slice 015)
  - signed chain tips detect truncation (slice 416)
- **Tests:** `test_sec_416_provenance_tamper`

### T-07 — Secrets leak into logs, errors, or telemetry

- **STRIDE:** information_disclosure · **Asset:** `secrets` · **Risk:** 4×5=20 · **Residual:** partial
- **Scenario:** API keys or tokens embedded in state end up in log lines, error details, or exported telemetry.
- **Mitigations:**
  - secret detection on outbound data (slice 234)
  - redaction pipeline (privacy fortress)
  - secret-handling audit gate (slice 421)
- **Tests:** `test_sec_421_secret_audit`

### T-08 — Replayed cluster RPC re-executes a decision

- **STRIDE:** spoofing · **Asset:** `cluster_traffic` · **Risk:** 2×4=8 · **Residual:** partial
- **Scenario:** A captured authenticated envelope is re-fired to repeat a privileged cluster operation.
- **Mitigations:**
  - per-sender sequence window rejects replays (slice 208)
  - nonce+timestamp replay guard (slice 418)
- **Tests:** `test_sec_418_replay`

### T-09 — Dependency confusion / compromised package

- **STRIDE:** tampering · **Asset:** `model_artifacts` · **Risk:** 2×5=10 · **Residual:** partial
- **Scenario:** A malicious or typosquatted package enters via an unconstrained index or unpinned requirement.
- **Mitigations:**
  - supply-chain policy: pinned deps, allowed indexes, license allowlist (slice 404)
  - dependency CVE scan (slice 403)
- **Tests:** `test_sec_403_depscan`, `test_sec_404_supply_chain`

### T-10 — Path traversal in pack/model file loading

- **STRIDE:** tampering · **Asset:** `model_artifacts` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** A crafted pack manifest or model path escapes the intended directory and reads/writes arbitrary files.
- **Mitigations:**
  - safe_join: resolve + jail all user paths (slice 412)
- **Tests:** `test_sec_412_path_guards`

### T-11 — Malicious backend exfiltrates or hangs

- **STRIDE:** elevation_of_privilege · **Asset:** `plugin_code` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** A registered backend opens sockets, writes files, or blocks forever during evaluate().
- **Mitigations:**
  - sandbox boundary: audit-hook denies subprocess/socket (slice 408)
  - timeout + bulkhead isolation (slices 021/chaos)
  - malicious-backend gauntlet fixtures (slice 415)
- **Tests:** `test_sec_408_sandbox`, `test_sec_415_malicious_backend`

### T-12 — Unauthenticated service access

- **STRIDE:** spoofing · **Asset:** `service_api` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** The HTTP service exposes decide/configure endpoints without authentication or authorization checks.
- **Mitigations:**
  - service AuthZ policy: roles + capabilities (slice 419)
  - cluster mutual auth for node traffic (slice 208)
- **Tests:** `test_sec_419_authz`
- **Rationale:** AuthZ policy ships deny-by-default; deployment wiring (TLS termination, key distribution) remains operator responsibility.

### T-13 — Credential-less rate exhaustion (DoS)

- **STRIDE:** denial_of_service · **Asset:** `service_api` · **Risk:** 4×3=12 · **Residual:** partial
- **Scenario:** An unauthenticated client floods /decide and starves legitimate users.
- **Mitigations:**
  - per-key token-bucket rate limiting (slice 420)
  - backpressure + bulkheads (slices 289/chaos)
- **Tests:** `test_sec_420_rate_limit`

### T-14 — Log injection forges audit entries

- **STRIDE:** spoofing · **Asset:** `provenance_chain` · **Risk:** 3×3=9 · **Residual:** partial
- **Scenario:** Newlines/control characters in user input create fake log lines that mimic system entries.
- **Mitigations:**
  - log sanitizer: strip control chars (slice 413)
  - structured JSON logging (slice 009)
- **Tests:** `test_sec_413_injection_corpus`

### T-15 — Untrusted plugin runs with full privileges

- **STRIDE:** elevation_of_privilege · **Asset:** `plugin_code` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** Any importable module can be registered as a backend with no trust distinction.
- **Mitigations:**
  - plugin trust levels + manifest signatures (slice 407)
- **Tests:** `test_sec_407_plugins`

### T-16 — Fuzz-found crash in parsers/validators

- **STRIDE:** denial_of_service · **Asset:** `decision_inputs` · **Risk:** 3×3=9 · **Residual:** partial
- **Scenario:** Malformed JSON/compact encodings crash serde or validation instead of raising taxonomy errors.
- **Mitigations:**
  - deterministic fuzz campaign over entry points (slice 422)
  - taxonomy-only raise discipline (slice 007)
- **Tests:** `test_sec_422_fuzzing`

### T-17 — Stale/vulnerable transitive dependency

- **STRIDE:** tampering · **Asset:** `model_artifacts` · **Risk:** 3×4=12 · **Residual:** partial
- **Scenario:** A pinned-but-vulnerable transitive dep ships a known CVE.
- **Mitigations:**
  - advisory DB scan in CI (slice 403)
- **Tests:** `test_sec_403_depscan`
- **Rationale:** Curated advisory DB covers direct deps; transitive closure auditing needs lockfile hashes, a later hardening pass.

### T-18 — Side-channel: timing reveals cache hits

- **STRIDE:** information_disclosure · **Asset:** `decision_cache` · **Risk:** 2×2=4 · **Residual:** accepted
- **Scenario:** Cache-hit vs miss timing lets an attacker probe whether a decision was recently made.
- **Rationale:** Local-first single-tenant threat model: attacker with timing access already has process access. Documented, not defended.
