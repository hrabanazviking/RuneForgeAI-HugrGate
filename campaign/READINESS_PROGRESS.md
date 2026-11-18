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

## Remaining
- HG-T4 … HG-T6 - not started.
- "Ready for Tviheimr" gate — not reached.
