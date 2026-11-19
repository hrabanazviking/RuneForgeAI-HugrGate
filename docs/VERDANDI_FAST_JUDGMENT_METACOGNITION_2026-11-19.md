# HugrGate integration: Verdandi fast reflex judgment and metacognitive observation

**Owner request:** 2026-11-19  
**Status:** optional integration roadmap; **do not claim HG-T4 live endpoint is operational without actual integration tests**  
**Verdandi source changes:** [Verdandi HugrGate + Metacognitive Roadmap](https://github.com/hrabanazviking/Verdandi/blob/feat/hugrgate-fast-reflex-metacognition-2026-11-19/docs/VERDANDI_HUGRGATE_METACOGNITION_SECOND_BRAIN_ROADMAP_2026-11-19.md).  
**Second Brain architecture:** [Bifröst Verdandi Observation Adapter](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/VERDANDI_OBSERVATION_REACTION_SECOND_BRAIN_INTEGRATION_2026-11-19.md).

## The existing contracts

Verdandi already provides `HugrGateJudge` in `reflex_judgment.py`: HTTP request with `reflex`, `trigger`, `action`, `event` and expects `{"reflex": name, "fire": bool, "basis": text, "judge": id}`. Its `JudgmentBinding` ensures malformed/dead/unreachable judges produce awareness-only no-fire. Verdandi's own [Tvíheimr readiness roadmap](https://github.com/hrabanazviking/Verdandi/blob/main/VERDANDI_TVIHEIMR_READINESS_ROADMAP.md) assigns the precise live API to **HG-T4**, but that project's roadmap is NOT proof of a verified public HugrGate server endpoint.

Verdandi's new opt-in `prefilter_unmatched=True` path avoids asking HugrGate for a verdict when the owner-declared trigger is deterministically false. Matching candidate actions still demand a valid positive response. New `metacognitive_observer.py` detects event pressure, repeated failures, apparent loops, latency anomalies, state changes, uncertain retrieval and reported source conflicts. Its optional `judge(summary)` accepts a **metadata-only** bounded summary and returns `{"escalate": bool, "basis": str, "confidence": number|null}`. This is an injected interface *for future HugrGate in-process/adapter integration*, not a claim that existing generic HugrGate endpoints speak it.

## HugrGate engineering additions, separately deployable

1. **HG-T4 exact schema verification:** version request and response; validate exact declared reflex name/action/trigger, owner grant, type constraints, rate limits, no arbitrary command execution and no schema trick permitting an unknown reflex to fire.
2. **Fast in-process judgment adapter:** provide a stable HugrGate SDK callable or local protected IPC method for high-frequency metadata decisions. This avoids HTTP round-trips when measured to be cheaper. May use existing rules/classifiers; no LLM merely for basic predicate matching.
3. **Batch eligible reflexes:** versioned batch API only for declarations that survive Verdandi's deterministic prefilter. Return a separate, attributed result for each input; fail closed on missing/malformed responses.
4. **Typed meta-observation judgment:** `metacognition_escalate`, `needs_deep_reflection`, `verification_depth`, `model_escalation`, `safe_response`, `focus_shift_suggestion`. All read-only judgment; no direct data writes, spawned processes or permissions changes.
5. **Privacy metadata allowlist:** no raw conversation, prompt, image bytes or private file paths in default summaries. Optional local evidence IDs only. Persist at most redacted operational counters; original short-term Bifröst content may not be saved in HugrGate decision histories.
6. **Circuit breaker, caching and load management:** match stable event IDs/hashes, bound retries/timeouts, protect Gufo Z13 foreground inference, do not lock Verdandi's fast UDS publish path while waiting on models.
7. **Confidence and abstention:** the judge must reject malformed input, unsupported request type, stale source/version, low confidence and unavailable models rather than issuing an invented approval.
8. **Cross-platform transport:** Verdandi may run on Pi for its original agent; Bifröst optional observer runs on G14. A private authenticated boundary to Z13 HugrGate is separately configured. No default public TCP listening.
9. **Telemetry and tests:** p50/p95/p99 judgment latency, avoided calls, event→proposal delay, false-fire/false-no-fire rates, detection usefulness, muted alert floods, source-of-truth invariants. Compare deterministic-only, HG-T4 HTTP, in-process and optional Gufo small model.
10. **Backward compatibility:** no forced changes to existing HugrGate APIs, NorseSagaEngine/Yggdrasil cognition routing, Bifröst archive, or other client application behavior. Feature flags and synthetic fixtures first.

## Bifröst three-tier and reactive cognition boundaries

- **Long-term Urðr:** Bifröst accepted immutable source versions and approved knowledge journal. HugrGate can report anomalies, cannot rewrite or delete these.
- **Medium-term Verðandi:** active projects/folders and changing focus priorities, optionally suggested by HugrGate. Changes reversible and separately authorized.
- **Short-term sessions:** volatile context expires; observation *metadata* may be transiently inspected but cannot become permanent chat content by using Verdandi's standard operational event feed or HugrGate's memory/logging subsystem.
- **Skuld:** bounded hypothetical outcomes and future reaction proposals, not certain prophecies or automatic permanent commits.
- **Yggdrasil 2.0/Mímir:** optional deep reflective follow-up chosen only when useful, not an LLM invoked for each nerve impulse.
- **Universal read-only Janitor/SillyTavern character access:** no per-character collection permissions; no write/action tokens exposed through shared retrieval API.

## Proof gates

- A stream with only a small percentage of matching reflex triggers skips irrelevant HG-T4 calls, returns the same expected actions and preserves no-fire safety.
- Failed/no judge: no reflex executes. Wrong reflex name: rejected. Urgent loop/flood: alerts rate-limited and never silently triggers a novel action.
- No permanent retention of short-term transcript sentinel in HG event decision memory, Verdandi JSONL or Bifröst journal.
- Gufo or HugrGate down: Verdandi bus remains fast; Bifröst search/ingest remains operational.
- Real benchmark establishes whether a service-vs-in-process backend is useful; no fabricated "N-times faster" claim.
- No private GitHub repo data, credentials, raw user text or absolute local paths committed publicly.

**Release:** coordinate HG-T4 with Verdandi's first code slice, prove fixture parity and live API compatibility, then separately enable tested optional Bifröst integration. This is a roadmap, not implementation evidence.
