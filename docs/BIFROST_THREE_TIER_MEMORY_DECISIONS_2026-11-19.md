# HugrGate: Optional Three-Tier Bifröst Memory Decision Layer

**Owner requirement date:** 2026-11-19  
**Status:** proposal and acceptance tests, NOT a live integration  
**Canonical architecture:** [Bifröst Three-Tier Memory](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_THREE_TIER_MEMORY_ARCHITECTURE_2026-11-19.md) plus [managed raw folders and duplicate-aware ingestion](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_MANAGED_RAW_LIBRARY_FOLDERS_2026-11-19.md).

## Scope

HugrGate is an **optional, local-first bounded judgment and routing engine**, not the canonical brain DB and not a reason to replace current Bifröst ingestion, Skein, Skry or already running Gufo.

A **three-tier memory contract** now applies:
- **Long-term**: accepted evidence and canonical lore are forever **immutable after archival**. No HugrGate decision, ML confidence score, inference routing choice, policy default or API handler may UPDATE/DELETE an original accepted record. Corrections produce new linked immutable versions under a separately authorized owner/Ingest workflow.
- **Medium-term**: current focus domains may change, become more/less relevant, be pinned or retired. HugrGate may issue bounded probability-bearing recommendations about likely domain, urgency, salience, work queue, duplicate-semantic-candidate or whether to use a stronger model. It does not automatically modify the permanent archive.
- **Short-term**: temporary request/task/session information changes constantly and must expire and be purged rather than persist. A decision ledger must not silently preserve entire short-term dialogue/contents forever; log safe provenance IDs, decision classes and bounded telemetry, using redaction/content minimization where available.

All private authorized Janitor AI and SillyTavern characters continue to have uniform broad **read-only** second-brain access. Neither classification confidence nor folder-domain labels create per-character collection restrictions.

## Useful bounded decisions

| Candidate decision | Deterministic-first or probabilistic? | Allowed side effect |
| --- | --- | --- |
| Unchanged file hash | Deterministic content hashing in Ingest; NO HugrGate or LLM required | No-op |
| File moved/copied with identical bytes | Deterministic source ledger and hash reconciliation; ambiguous cases flagged | Update mutable paths/associations only after valid reconciliation |
| Classify new file to suggested owner folder/category | Rule/classifier/HugrGate ranking, abstain on ambiguous | Suggest metadata/category in medium focus; no raw file relocation |
| Recognize active research/project focus | Bounded class/salience decision | Suggest medium domain priority; owner/trusted workstream approves changes |
| Detect image requiring deep visual description | MIME/rules first; uncertain cases score via HugrGate | Route changed asset to Z13 vision inference worker |
| Select lightweight versus heavyweight model | Cost/latency/accuracy threshold and availability | Schedule a permitted Gufo service operation, never a public credential leak |
| Potential factual contradiction or visual canon drift | Evidenced candidate score with abstention | Flag for review. NO automatic mutation of immutable lore |
| Promote medium working result to permanent | HugrGate may provide confidence/provenance assessment | **Recommendation only**; explicit owner/Ingest archival action |
| Short-term session expired | Deterministic TTL and session-end event | Purge volatile local state; no permanent decision-event copy containing transcript |
| Model resource/quiet scheduling | Deterministic policy then optional uncertainty judgment | Request/defer work; no direct raw source deletion |

## Integration constraints

- [ ] Integrate inside Bifröst as an **optional adapter**, first in-process for lightweight rules where validated. Existing project interfaces, APIs and standalone tools must remain independent.
- [ ] When direct service mode is selected, use local unix socket or owner-approved protected transport; HugrGate's plain HTTP daemon documentation describes no built-in authentication, so never expose it to Janitor or the public Internet.
- [ ] Prevent default persistent recording of short-term conversation payloads in HugrGate's DecisionHistory, provenance, episode memory, logs, caches, benchmark exports or remote telemetry. Select a privacy-class/redacted view, content-digest-only records or disable ledger for ephemeral tasks. Purge where appropriate. This requires verification against real running configs, not trust in documentation slogans.
- [ ] Gate all proposed archive writes through separately authenticated explicit owner workflows. "Confidence: 0.99" is still a guess, never authorization to rewrite permanent facts.
- [ ] Avoid implementing new duplicate-detection rules inside HugrGate if Bifröst already has exact hashes and a source-instance ledger. Judgment may only address genuinely ambiguous semantic/domain cases.
- [ ] Honor G14 resource limits and Z13 Gufo shared inference priorities; interactive chat remains ahead of background multimodal reclassification and promotion review jobs.
- [ ] Preserve current Gufo service lifecycle and API mapping; add a verified API adapter only if a specific supported model judgment is justified.
- [ ] Respect existing Raven associations as separate mutable medium-term signals; no uncontrolled cross-backend writes. Do not substitute learned recency/importance for evidentiary truth.
- [ ] Publish decision explanation, version, confidence/calibration, abstention and non-sensitive input identifier; never copy raw temporary sessions into an indefinite audit trail.

## Tests and proof

1. A HugrGate response can mark a candidate as plausible but cannot change the canonical long-term archive with any supplied API token or integration role.
2. Changing a medium focus tag updates only a mutable focus ledger; original permanent evidence hashes stay identical.
3. A short-term session, intentionally filled with a sentinel string, expires; neither default logs, episodic memory, decision history, JSONL exports, backups nor crash recovery contain it afterward. Review and adapt existing HugrGate persistence modules where needed.
4. Deterministic unchanged hash and unambiguous move/copy processing use zero additional model calls.
5. Confidence error/abstention safely routes disputed visual attributes and contradictions to owner review, never to archive overwrite.
6. Janitor gateway remains read-only and works if HugrGate module is disabled or unavailable.
7. Actual Z13 model calls and G14 decision scheduling are benchmarked for correctness and overhead; use deterministic rules when sufficient.

**Delivery:** review existing HugrGate decision/episode-memory code, write Bifröst adapter contracts, add isolated synthetic tests, benchmark, then request owner-approved deployment. This plan is not implementation evidence.
