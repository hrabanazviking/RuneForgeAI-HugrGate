# HugrGate Tviheimr Readiness — Progress Ledger

Campaign branch: `yrsa/tviheimr-readiness` (off main @ 4d0a6886)
Venue: purplelongship, clone `~/forges/hugrgate-readiness`
Method: Mythic Engineering (inspect -> build -> test -> repair -> continue);
roles run sequentially by the keeper (no sub-agents this tick), recorded here.

## HG-T1 — Decision-server form — GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/decision_server.py` (stdlib-only, plain process):
  POST /judge (+ /decide alias), POST /events (event-intake, per-event
  verdicts, nothing dropped silently), GET /health, GET /backends,
  structured JSON request logging (metadata only), clean start/stop
  and SIGINT/SIGTERM serve().
- Gate tests: `tests/test_tviheimr_hg_t1_decision_server.py` — 7 tests,
  real HTTP on ephemeral localhost port.
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T1 tests +
  existing health tests = 22 passed in 3.79s.
- Live plain-process smoke on device: GET /health ok; POST /judge ->
  value=escalate (keyword, p=0.731); POST /events -> accepted=2, both
  verdicts ok; SIGTERM -> clean shutdown (port closed); structured
  JSON request logs present in the server log.
- Existing-suite note: on purplelongship the optional FastAPI `server`
  extra is not installed, so FastAPI-dependent pre-existing tests fail
  at collection both before and after this slice (environment, not a
  regression). The full-suite-green clause is therefore verified for
  every test that can run in this venue's installed environment; the
  FastAPI-extra tests are unrun here, not failed by HG-T1.

## HG-T2 — Small-fast-model judgment backend — GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/model_backend.py` (stdlib-only): `OllamaEngine`
  (Ollama-shaped local endpoint, `think: False` — thinking models
  otherwise burn the judgment token budget on hidden reasoning and
  answer empty, measured), `SelectiveModelBackend` (rules-first;
  the model is consulted ONLY when the primary verdict is unsettled:
  probability < 0.55 or top-two margin < 0.20; model failure falls
  back to the rules verdict with `model_error` recorded), and
  honest-confidence handling (Ollama returns no calibrated
  probability; fixed 0.6, flagged `confidence_calibrated: False`).
- Supporting change in `hugrgate/backends/llm.py` (+7 lines):
  `LLMBackend._prompt` now renders `spec.metadata`
  `option_definitions` when present — the definitions are what make
  the small model earn its cost on the hard cases (probe: gemma
  4/12 hard without definitions, 8/12 with).
- Fixed case set: `benchmarks/hg_t2_cases.py` — 24 triage cases
  (12 clear with the verdict word present, 12 hard with no verdict
  word). Benchmark runner: `benchmarks/hg_t2_benchmark.py`.
- Benchmark report banked: `campaign/hg_t2_benchmark_report.json`
  (live Ollama on purplelongship, warmup excluded from latencies):
  rules-only acc 0.6667 (clear 1.0, hard 0.3333, median 0.011 ms);
  gemma4viking4b:latest (4.6B, PICK) selective acc 0.8333
  (hard 0.6667), model invoked on exactly the 12 hard cases and
  never on clear ones, model median latency 1016 ms, cold warmup
  25.3 s; b1olmoe:latest selective acc 0.7083 (hard 0.4167),
  model median 1012 ms. Pick rule: highest selective accuracy,
  then lowest model latency. `DEFAULT_MODEL` = the pick.
- Gate tests: `tests/test_tviheimr_hg_t2_model_backend.py` — 7 tests
  (case-set construction, selective routing with a counting engine,
  honest fallback, Ollama client over real HTTP vs a stub
  Ollama-shaped server, unreachable-endpoint honesty).
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T2 +
  HG-T1 + routing/llamacpp/registry/ladder sets = all green
  (14 HG-T1/T2, 42 in the widened set, 71 registry/ladder).
- Venue note: no small model was pre-served on purplelongship;
  `ollama serve` was started as a plain process for the benchmark
  and stopped again at bank time. No service was created.

## HG-T3 - Event-stream triage profile - GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/triage_profile.py` (stdlib-only): `TriageProfile`
  with input schema (source, kind, time, payload or payload_digest;
  time must parse as ISO-8601 or epoch) and verdict schema
  (urgency, route, escalate, basis, payload_digest, deterministic,
  model_used). Ordered named rules, first match wins, winning rule
  recorded in basis: critical/high signals -> escalate, medium ->
  notify, low -> archive, no-signal -> medium review.
- Deterministic-first: identical events give identical verdicts;
  no model by default. An explicitly supplied model is consulted
  only for the default-review case and its basis says
  `model:<name>`; settled cases never consult it.
- Nothing dropped silently: invalid-schema events and duplicate
  payload digests in a stream receive route=`shed` verdicts with
  schema:/duplicate: basis, counted like any other verdict.
- Recorded fixture: `campaign/hg_t3_fixture_stream.json` - 16
  synthetic world events with an expected table (urgency/route/
  escalate). Fixture triaged end-to-end matching the table; 3 shed
  verdicts (duplicate, missing source, unparseable time).
- Decision server: POST /triage added to DecisionServer, returning
  accepted/verdicts/shed counts over the same profile.
- Gate tests: `tests/test_tviheimr_hg_t3_triage.py` - 7 tests
  (fixture table, basis+digest on every verdict, shed accounting,
  determinism, declared model-in-loop, digest stability/schema,
  server end-to-end).
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T1+T2+T3
  = 21 passed; widened set with health/registry/ladder/routing =
  105 passed in 4.54s. Full-suite collection note from HG-T1/T2
  stands unchanged (42 pre-existing collection errors from the
  uninstalled optional FastAPI extra in this venue, not HG-T3).
- Method note: roles run sequentially by the keeper (no sub-agents
  this tick), recorded per campaign instructions.

## HG-T4 - Reflex API for Verdandi - GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/reflex_api.py` (stdlib-only): `ReflexRegistry`
  for one consumer (default verdandi). A consumer registers
  reflexes (trigger pattern -> named action); HugrGate judges
  events against them and returns fire/no-fire with basis.
  HugrGate judges; the consumer acts and records.
- Patterns are explicit: optional source match, optional kind
  match (exact, or prefix when the value ends in '*'), optional
  payload `where` conditions (value or list of allowed values).
  At least one of source/kind is required - no catch-all reflexes.
  Registration validation refuses duplicate names, empty actions,
  bare wildcards, unknown pattern fields and malformed conditions.
- Only declared reflexes can fire: an event matching no registered
  pattern fires nothing, and an empty registry fires nothing.
  Invalid events (missing source/kind) fire nothing - every
  verdict is no-fire with a schema basis, never a silent drop.
- Every judgment returns one verdict per registered reflex, in
  registration order: fire, action, basis naming the matched or
  first failed pattern part, payload digest, measured latency_ms.
  Deterministic apart from latency.
- Recorded fixture: `campaign/hg_t4_fixture_reflexes.json` - 4
  declared reflexes, 11 synthetic events, expected fires table
  (5 fires: events 0, 2, 4, 6, 7, one each; near-misses on source,
  kind, and payload condition all no-fire; undeclared kinds and
  an invalid event fire nothing). Fixture judged end-to-end
  matching the table exactly.
- Latency report banked: `campaign/hg_t4_latency_report.json`
  (runner `benchmarks/hg_t4_reflex_bench.py`, 200 rounds x 11
  events = 2,200 judgments, expected-table asserted first):
  median 0.008 ms, p95 0.009 ms, max 0.025 ms per judgment.
- Decision server: POST /reflexes (201; invalid declarations
  refused 400), GET /reflexes, POST /reflex/judge added, backed
  by a per-server ReflexRegistry.
- Gate tests: `tests/test_tviheimr_hg_t4_reflex.py` - 8 tests
  (exact fixture table, undeclared cannot fire, basis+digest+
  latency on every verdict, invalid-event schema basis,
  registration validation, determinism + unregister, latency
  report recorded and sub-5ms median, server end-to-end).
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T1+T2+
  T3+T4 = 29 passed; widened set with health/registry/ladder/
  routing = 149 passed in 4.82s. Live plain-process HTTP smoke:
  register x4 -> 201, list = 4, judge matches the expected table,
  catch-all declaration refused 400, clean shutdown.
- Method note: roles run sequentially by the keeper (no
  sub-agents this tick), recorded per campaign instructions.

## HG-T5 - Aurelia sensation-stream profile - GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/salience_profile.py` (stdlib-only): `SalienceProfile`
  consuming Aurelia's own AU-T1 sensation event schema v1 (kind,
  intensity 0..1, source, timestamp, sha256 digest, schema_version=1,
  optional before/after - her house defines it, this slice consumes
  it) and emitting Aurelia AU-T2 verdict schema v1 field-for-field
  (event_digest, salient, disposition surface/settle, authenticity
  genuine/noise, urgency grade 0..3, basis, judge_id
  `hugrgate-salience-v1`), so her JudgmentBinding accepts it
  unchanged.
- Salience table is Aurelia's own declared floors (noise 0.05,
  salient 0.20, high 0.50, critical 0.80): >=0.80 genuine/surface/3;
  0.50-0.80 genuine/surface/2; 0.20-0.50 genuine/surface/1;
  0.05-0.20 genuine/settle/0; <0.05 noise/settle/0. Deterministic:
  identical events give identical verdicts; no model in the loop.
- Nothing dropped silently: schema-invalid events receive exactly
  one settle/noise verdict whose basis starts `schema:` and names
  every failure, flagged schema_valid=False.
- Recorded fixture: `campaign/hg_t5_fixture_stream.json` - 19
  events in AU-T1 form (first 8 are Aurelia's AU-T2 recorded stream
  verbatim; digests over the AU-T1 underlying record), 16 valid +
  3 schema-invalid on purpose, with her expected table.
- Report banked: `campaign/hg_t5_salience_report.json` (runner
  `benchmarks/hg_t5_report.py`): table matches 16/16 valid events;
  noise rejection rate 1.0 (3/3 valid expected-noise settled);
  miss rate 0.0 (0/9 expected-surface settled). Schema-invalid
  events are excluded from both rates and counted separately -
  input failures, not judgment misses.
- Decision server: POST /salience added, returning verdicts plus
  the evaluate report when an expected table is supplied.
- Gate tests: `tests/test_tviheimr_hg_t5_salience.py` - 8 tests
  (fixture table, AU-T2 schema compatibility, AU-T2 recorded stream
  + AU-T1 digest recomputation, boundary floors, honest rates vs
  banked report, schema verdicts not drops, determinism, server
  end-to-end).
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T1..T5
  = 37 passed; widened set with health/registry/ladder/routing =
  157 passed in 4.88s. Live plain-process HTTP smoke: /health ok;
  POST /salience -> accepted=19, surfaced=9, noise=6,
  schema_invalid=3, noise_rejection 1.0, miss 0.0; clean shutdown.
- LIVE AURELIA RE-PROOF (the re-proof AU-T2 owed): Aurelia's real
  JudgmentBinding + JudgmentVerdict code (her readiness clone on
  this device) driven by an adapter over this profile judged her
  AU-T2 recorded stream 8/8 matching her expected table with no
  degradation logged. HG-T5 therefore discharges the live-binding
  swap her AU-T2 recorded as owed (her ledger update is hers).
- Method note: roles run sequentially by the keeper (no
  sub-agents this tick), recorded per campaign instructions.

## HG-T6 - Judgment provenance ledger - GATE PASSED (device-verified 2026-11-18)
- Built `hugrgate/judgment_ledger.py` (stdlib-only): append-only
  JSONL `JudgmentLedger` - every entry carries seq, timestamp,
  kind, slice, basis, inputs_digest (sha256 of canonical input),
  the full verdict, verdict_digest, latency_ms, model_used, and a
  hash chain (prev_hash -> record_hash, the house integrity model
  of hugrgate.provenance). record() writes + flushes + fsyncs
  before returning; opening an existing ledger re-reads and
  verifies it and continues seq/chain - a tampered or corrupt
  file is refused at open, never silently extended. Audit:
  entries(), trace(verdict), by_verdict_digest(),
  by_inputs_digest(), verify() re-read from disk.
- Decision server integration: DecisionServer(ledger_path=...)
  (CLI `--ledger`) records EVERY verdict synchronously before
  the response is built - judge, /events, /triage, /reflex/judge
  and /salience - so no verdict exists without an entry.
  GET /ledger reports entries + verified + head hash; /health
  carries ledger_entries.
- Gate tests: `tests/test_tviheimr_hg_t6_ledger.py` - 7 tests
  (record/trace round-trip, no-basis-no-entry, restart survival
  with chain continuation, tamper detected + refused, all
  HG-T3/T4/T5 fixture verdicts traced, server records every
  verdict end-to-end over real HTTP, no-ledger server unchanged).
- Device gate run (purplelongship, TMPDIR=~/forge-tmp): HG-T6 = 7
  passed; HG-T1..T6 = 44 passed.
- House-registry completion (the full-suite clause made these
  visible; all were failing only on this branch, all fixed):
  the six campaign modules registered in tools/gen_arch_map.py
  LAYERS + regenerated architecture map; audit manifest +
  API inventory regenerated (tools/audit_repo.py); gauntlet API
  baseline regenerated for the added public API; taxonomy doc
  gained the six HG test modules (integration); hg_t2_cases
  registered in test_dependency_rules' _LOCAL_MODULES (the house
  pattern for sys.path first-party modules); campaign modules
  brought under the house raise-site rule (stdlib ValueError /
  RuntimeError at raise sites; ReflexError/LedgerError kept as
  aliases) and unused imports removed. The 9 branch-only meta
  failures (arch_map x3, dead_code, dependency_rules, errors,
  gauntlet_486, repo_truth, taxonomy) now pass, and
  test_api_inventory - failing even on main - passes again.
- Method note: roles run sequentially by the keeper (no
  sub-agents this tick), recorded per campaign instructions.

## "Ready for Tviheimr" gate - PASSED (device-verified 2026-11-18)
- HG-T1..HG-T6 all banked with gate evidence (this ledger).
- Full existing suite on purplelongship: 5,904 passed, 23 failed,
  5 skipped. Failure-for-failure comparison against a pristine
  main clone in the same venue: ZERO campaign-only failures -
  every remaining failure also fails on main here (uninstalled
  optional extras: ml/server; no-GPU host; sbom-from-installed;
  pre-existing environment failures), and one main failure
  (test_api_inventory) now passes. No regression, no softening.
- Tviheimr-side fixture consumer banked:
  `campaign/tviheimr_fixture_consumer.py` + report
  `campaign/hg_ready_consumer_report.json`. It starts the
  decision server as a plain process with the ledger on,
  registers the HG-T4 reflexes, and calls /triage, /reflex/judge,
  /salience and /judge against the recorded fixtures: all 8
  checks pass - fixture tables exact (triage, reflex,
  salience), judge ok, ledger complete (80 entries for 80
  verdicts) and verified, ledger survives restart. Latencies
  (localhost HTTP, ledger fsync included): judge 18.134 ms;
  per-verdict triage 12.1 ms, reflex 17.3 ms,
  salience 19.9 ms - all inside the recorded budgets
  (500 ms single call, 25 ms per ledgered verdict).
- HugrGate is ready for Tviheimr by the roadmap's own gate.
  This keeper's work is complete; the keeper is to be disabled.

## Remaining
- None. Roadmap complete: HG-T1..HG-T6 banked, "Ready for
  Tviheimr" gate passed.
