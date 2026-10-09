# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T17:21:07.102432+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 313 Python files under `hugrgate/`
- **Total LOC:** 70808
- **pyproject version:** 0.1.0
- **Test files:** test_adaptive_bandit.py, test_adaptive_benchmark.py, test_adaptive_coldstart.py, test_adaptive_competence.py, test_adaptive_contract_competence.py, test_adaptive_cost_quality.py, test_adaptive_counterfactual.py, test_adaptive_delayed.py, test_adaptive_domain_competence.py, test_adaptive_drift.py, test_adaptive_energy_quality.py, test_adaptive_explanations.py, test_adaptive_exploration.py, test_adaptive_feedback.py, test_adaptive_latency_quality.py, test_adaptive_multiobjective.py, test_adaptive_offline.py, test_adaptive_privacy_objective.py, test_adaptive_rollback.py, test_adaptive_router_features.py, test_adaptive_safe_exploration.py, test_adaptive_shadow.py, test_adaptive_telemetry.py, test_adaptive_versioning.py, test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_calib_adversarial.py, test_calib_aleatoric.py, test_calib_autoselect.py, test_calib_bayes.py, test_calib_bench.py, test_calib_conformal.py, test_calib_conformal_reg.py, test_calib_coverage.py, test_calib_decomposition.py, test_calib_drift.py, test_calib_ensemble.py, test_calib_epistemic.py, test_calib_group.py, test_calib_imbalance.py, test_calib_online.py, test_calib_perclass.py, test_calib_pipeline.py, test_calib_registry.py, test_calib_risk_coverage.py, test_calib_selective.py, test_calib_sets.py, test_calib_shift.py, test_calib_viz.py, test_calib_window.py, test_chaos_backend_crash.py, test_chaos_backend_hang.py, test_chaos_bulkhead.py, test_chaos_cache_corruption.py, test_chaos_clock_skew.py, test_chaos_corrupt_model.py, test_chaos_cpu_starvation.py, test_chaos_crash.py, test_chaos_degradation.py, test_chaos_dependency_matrix.py, test_chaos_disk_full.py, test_chaos_error_rate.py, test_chaos_framework.py, test_chaos_latency.py, test_chaos_malformed.py, test_chaos_memory_pressure.py, test_chaos_network_flap.py, test_chaos_network_loss.py, test_chaos_partial_service.py, test_chaos_readonly_fs.py, test_chaos_recovery.py, test_chaos_retry_budget.py, test_chaos_scorecard.py, test_chaos_soak.py, test_cluster_auth.py, test_cluster_backpressure.py, test_cluster_bench.py, test_cluster_capabilities.py, test_cluster_chaos.py, test_cluster_discovery.py, test_cluster_distributed_batch.py, test_cluster_identity.py, test_cluster_lan.py, test_cluster_node_cost.py, test_cluster_node_health.py, test_cluster_node_latency.py, test_cluster_partition.py, test_cluster_policy_sync.py, test_cluster_privacy_boundary.py, test_cluster_protocol.py, test_cluster_provenance_dist.py, test_cluster_recovery.py, test_cluster_release_gate.py, test_cluster_routing.py, test_cluster_rpc.py, test_cluster_static_config.py, test_cluster_trace.py, test_cluster_transport.py, test_cluster_work_stealing.py, test_config.py, test_contracts_026.py, test_contracts_027.py, test_contracts_028.py, test_contracts_029.py, test_contracts_030.py, test_contracts_031.py, test_contracts_032.py, test_contracts_033.py, test_contracts_034.py, test_contracts_035.py, test_contracts_036.py, test_contracts_037.py, test_contracts_038.py, test_contracts_039.py, test_contracts_040.py, test_contracts_041.py, test_contracts_042.py, test_contracts_043.py, test_contracts_044.py, test_contracts_045.py, test_contracts_046.py, test_contracts_047.py, test_contracts_048.py, test_contracts_049.py, test_contracts_050.py, test_coverage_attack.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_edge_affinity.py, test_edge_bench.py, test_edge_bootstrap.py, test_edge_cachetune.py, test_edge_chaos.py, test_edge_gate.py, test_edge_memory.py, test_edge_npu.py, test_edge_platform.py, test_edge_power.py, test_edge_quant.py, test_edge_recovery.py, test_edge_residency.py, test_edge_storage.py, test_edge_telemetry.py, test_edge_thermal.py, test_edge_watchdog.py, test_ensemble_101_api.py, test_ensemble_102_hard_voting.py, test_ensemble_103_soft_voting.py, test_ensemble_104_weighted_voting.py, test_ensemble_105_confidence_voting.py, test_ensemble_106_bma.py, test_ensemble_107_stacking.py, test_ensemble_108_blending.py, test_ensemble_109_moe.py, test_ensemble_110_diversity.py, test_ensemble_111_disagreement.py, test_ensemble_112_escalation.py, test_ensemble_113_consensus.py, test_ensemble_114_minority.py, test_ensemble_115_correlation.py, test_ensemble_116_reliability.py, test_ensemble_117_membership.py, test_ensemble_118_calibration.py, test_ensemble_119_provenance.py, test_ensemble_120_explanations.py, test_ensemble_121_caching.py, test_ensemble_122_batch.py, test_ensemble_123_adversarial.py, test_ensemble_124_benchmarks.py, test_ensemble_125_release.py, test_errors.py, test_evlab_351_api.py, test_evlab_352_manifest.py, test_evlab_353_versioning.py, test_evlab_354_provenance.py, test_evlab_355_splits.py, test_evlab_356_stratified.py, test_evlab_357_crossval.py, test_evlab_358_bootstrap.py, test_evlab_359_significance.py, test_evlab_360_compare.py, test_evlab_361_calibration.py, test_evlab_362_selective.py, test_evlab_363_costaware.py, test_evlab_364_latency.py, test_evlab_365_energy.py, test_evlab_366_privacy.py, test_evlab_367_robustness.py, test_evlab_368_shift.py, test_evlab_369_fairness.py, test_evlab_370_history.py, test_evlab_371_artifacts.py, test_evlab_372_repro.py, test_evlab_373_gates.py, test_evlab_374_report.py, test_evlab_375_release.py, test_foundation.py, test_import_cycles.py, test_ladder.py, test_localrt_151_interface.py, test_localrt_152_llamacpp.py, test_localrt_153_ollama.py, test_localrt_154_onnx.py, test_localrt_155_transformers.py, test_localrt_156_vllm.py, test_localrt_157_mlx.py, test_localrt_158_openvino.py, test_localrt_159_tensorrt.py, test_localrt_160_gguf.py, test_localrt_161_metadata.py, test_localrt_162_probe.py, test_localrt_163_structured.py, test_localrt_164_grammar.py, test_localrt_165_jsonschema.py, test_localrt_166_nli_packs.py, test_localrt_167_embedding_packs.py, test_localrt_168_classifier_packs.py, test_localrt_169_warmup.py, test_localrt_170_residency.py, test_localrt_171_eviction.py, test_localrt_172_health_probes.py, test_localrt_173_conformance.py, test_localrt_174_bench_matrix.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_perf_276_profiling.py, test_perf_277_flame.py, test_perf_278_hotpaths.py, test_perf_279_allocprof.py, test_perf_280_zerocopy.py, test_perf_281_serde.py, test_perf_282_async_core.py, test_perf_283_async_api.py, test_perf_284_ladder_concurrent.py, test_perf_285_scheduler.py, test_perf_286_dynamic_batch.py, test_perf_287_priority.py, test_perf_288_deadline.py, test_perf_289_backpressure.py, test_perf_290_pool.py, test_perf_291_session_pool.py, test_perf_292_cache_tuning.py, test_perf_293_lockaudit.py, test_perf_294_multiproc.py, test_perf_295_supervision.py, test_perf_296_numa.py, test_perf_297_gpusched.py, test_perf_298_perfgate.py, test_perf_299_millionbench.py, test_policy_invariants.py, test_privacy_audit.py, test_privacy_bench_249.py, test_privacy_classification.py, test_privacy_crypto.py, test_privacy_deletion.py, test_privacy_dryrun.py, test_privacy_exfil.py, test_privacy_explain.py, test_privacy_flow.py, test_privacy_fortress_gate.py, test_privacy_fuzz.py, test_privacy_jurisdiction.py, test_privacy_keys.py, test_privacy_labels.py, test_privacy_localonly.py, test_privacy_minimize.py, test_privacy_payload.py, test_privacy_pii.py, test_privacy_provenance.py, test_privacy_redact.py, test_privacy_retention.py, test_privacy_sealed.py, test_privacy_secrets.py, test_privacy_tokens.py, test_privacy_trust.py, test_provenance_integrity.py, test_release_gate.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_routing_051.py, test_routing_052.py, test_routing_053.py, test_routing_054.py, test_routing_055.py, test_routing_056.py, test_routing_057.py, test_routing_058.py, test_routing_059.py, test_routing_060.py, test_routing_061.py, test_routing_062.py, test_routing_063.py, test_routing_064.py, test_routing_065.py, test_routing_066.py, test_routing_067.py, test_routing_068.py, test_routing_069.py, test_routing_070.py, test_routing_071.py, test_routing_072.py, test_routing_073.py, test_routing_074.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_static_analysis.py, test_taxonomy.py, test_thread_safety.py, test_typecheck.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 45 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 111 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.adaptive.__init__` | 211 | Adaptive routing (Campaign VI) — learn which inference path fits each wo | hugrgate |
| `hugrgate.adaptive.bandit` | 278 | Contextual bandit adapter. Slice 130. | hugrgate |
| `hugrgate.adaptive.benchmark` | 192 | Adaptive routing benchmark. Slice 149. | hugrgate |
| `hugrgate.adaptive.coldstart` | 154 | Cold-start routing. Slice 140. | hugrgate |
| `hugrgate.adaptive.competence` | 215 | Backend competence profiles. Slice 137. | hugrgate |
| `hugrgate.adaptive.contract_competence` | 172 | Per-contract competence. Slice 139. | hugrgate |
| `hugrgate.adaptive.cost_quality` | 139 | Cost-quality objective. Slice 132. | hugrgate |
| `hugrgate.adaptive.counterfactual` | 178 | Counterfactual route evaluation. Slice 144. | hugrgate |
| `hugrgate.adaptive.delayed` | 171 | Delayed-label ingestion. Slice 128. | hugrgate |
| `hugrgate.adaptive.domain_competence` | 169 | Per-domain competence. Slice 138. | hugrgate |
| `hugrgate.adaptive.drift_detect` | 184 | Adaptive-route drift detection. Slice 148. | hugrgate |
| `hugrgate.adaptive.energy_quality` | 127 | Energy-quality objective. Slice 134. | hugrgate |
| `hugrgate.adaptive.explanations` | 189 | Adaptive-route explanations. Slice 147. | hugrgate |
| `hugrgate.adaptive.exploration` | 171 | Exploration controls. Slice 141. | hugrgate |
| `hugrgate.adaptive.feedback` | 165 | Outcome feedback API. Slice 127. | hugrgate |
| `hugrgate.adaptive.latency_quality` | 153 | Latency-quality objective. Slice 133. | hugrgate |
| `hugrgate.adaptive.multiobjective` | 137 | Multi-objective routing. Slice 136. | hugrgate |
| `hugrgate.adaptive.offline` | 149 | Offline policy learning. Slice 131. | hugrgate |
| `hugrgate.adaptive.privacy_objective` | 114 | Privacy-constrained objective. Slice 135. | hugrgate |
| `hugrgate.adaptive.rollback` | 146 | Router rollback. Slice 145. | hugrgate |
| `hugrgate.adaptive.router_features` | 192 | Router feature extraction. Slice 129. | hugrgate |
| `hugrgate.adaptive.safe_exploration` | 127 | Safe exploration. Slice 142. | hugrgate |
| `hugrgate.adaptive.shadow` | 136 | Router shadow mode. Slice 143. | hugrgate |
| `hugrgate.adaptive.telemetry` | 360 | Routing telemetry dataset. Slice 126. | hugrgate |
| `hugrgate.adaptive.versioning` | 175 | Adaptive policy versioning. Slice 146. | hugrgate |
| `hugrgate.allocprof` | 281 | Allocation profiling — tracemalloc integration for decisions. Slice 279. | hugrgate |
| `hugrgate.async_backend` | 229 | Public async API surface. Slice 283. | hugrgate |
| `hugrgate.asyncx` | 106 | True-async backend evaluation for the decide path. Slice 282. | hugrgate |
| `hugrgate.backend` | 151 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 69 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 260 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 74 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 237 | Local LLM backend — constrained decoding. Slice 35; slice 152 rewire. | hugrgate |
| `hugrgate.backends.logreg` | 304 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 153 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 381 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.backpressure` | 207 | Local backpressure engine — admission control for hot paths. Slice 289. | hugrgate |
| `hugrgate.bench` | 345 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 146 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 300 | Decision cache — request-hash keyed result memoization. Slice 38; | hugrgate |
| `hugrgate.calibration.__init__` | 106 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 121 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.adversarial` | 170 | Calibration adversarial tests. Slice 098. | hugrgate |
| `hugrgate.calibration.aleatoric` | 133 | Aleatoric uncertainty adapters. Slice 096. | hugrgate |
| `hugrgate.calibration.autoselect` | 155 | Calibration auto-selection. Slice 092. | hugrgate |
| `hugrgate.calibration.bayes` | 181 | Bayesian calibration research adapter. Slice 081. | hugrgate |
| `hugrgate.calibration.bench` | 157 | Calibration benchmark suite. Slice 099. | hugrgate |
| `hugrgate.calibration.conformal` | 156 | Split-conformal classification. Slice 082. | hugrgate |
| `hugrgate.calibration.conformal_regression` | 143 | Split-conformal regression. Slice 083. | hugrgate |
| `hugrgate.calibration.coverage` | 168 | Coverage guarantees tooling. Slice 085. | hugrgate |
| `hugrgate.calibration.decomposition` | 113 | Uncertainty decomposition. Slice 094. | hugrgate |
| `hugrgate.calibration.drift` | 182 | Calibration under drift. Slice 088. | hugrgate |
| `hugrgate.calibration.ensemble` | 134 | Calibration ensemble. Slice 093. | hugrgate |
| `hugrgate.calibration.epistemic` | 138 | Epistemic uncertainty adapters. Slice 095. | hugrgate |
| `hugrgate.calibration.group` | 157 | Group calibration. Slice 078. | hugrgate |
| `hugrgate.calibration.imbalance` | 178 | Calibration under class imbalance. Slice 089. | hugrgate |
| `hugrgate.calibration.isotonic` | 112 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 149 | Calibration metrics. Slice 28. | hugrgate |
| `hugrgate.calibration.online` | 179 | Online (incremental) calibration. Slice 079. | hugrgate |
| `hugrgate.calibration.perclass` | 233 | Per-class calibration. Slice 077. | hugrgate |
| `hugrgate.calibration.pipeline` | 245 | Calibration pipeline (architecture v2). Slice 076. | hugrgate |
| `hugrgate.calibration.platt` | 131 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 277 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.registry` | 172 | Calibration registry (rich catalog). Slice 091. | hugrgate |
| `hugrgate.calibration.risk_coverage` | 147 | Risk-coverage curves. Slice 087. | hugrgate |
| `hugrgate.calibration.selective` | 125 | Selective prediction curves. Slice 086. | hugrgate |
| `hugrgate.calibration.sets` | 188 | Prediction sets. Slice 084. | hugrgate |
| `hugrgate.calibration.shift` | 165 | Calibration under distribution shift. Slice 090. | hugrgate |
| `hugrgate.calibration.temperature` | 137 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.calibration.viz` | 171 | Calibration visualization data. Slice 097. | hugrgate |
| `hugrgate.calibration.window` | 160 | Sliding-window calibration. Slice 080. | hugrgate |
| `hugrgate.chaos.__init__` | 172 | Reliability & chaos engineering. Campaign XI (slices 251-275). | hugrgate |
| `hugrgate.chaos.backend_faults` | 311 | Backend fault injection — crash, hang, latency, error-rate, and | hugrgate |
| `hugrgate.chaos.bulkhead` | 126 | Bulkheads: per-backend concurrency caps (slice 269). | hugrgate |
| `hugrgate.chaos.cache_faults` | 77 | Cache corruption simulation. Slice 258. | hugrgate |
| `hugrgate.chaos.clock` | 142 | Clock-skew simulation and audit. Slice 265. | hugrgate |
| `hugrgate.chaos.crash` | 165 | Crash-only restart: kill -9 the worker, recover from the journal (slice  | hugrgate |
| `hugrgate.chaos.degradation` | 272 | Degradation plans: ordered playbooks for failure modes (slice 270). | hugrgate |
| `hugrgate.chaos.experiments` | 499 | Ready-made chaos experiments. Slices 266-267. | hugrgate |
| `hugrgate.chaos.filesystem` | 81 | Filesystem fault simulation. Slices 259-260. | — |
| `hugrgate.chaos.framework` | 314 | Chaos experiment framework. Slice 251. | hugrgate |
| `hugrgate.chaos.model_faults` | 159 | Corrupt-model simulation. Slice 257. | hugrgate |
| `hugrgate.chaos.network` | 205 | Network fault simulation. Slices 263-264. | hugrgate |
| `hugrgate.chaos.recovery` | 224 | Recovery verification: post-fault probes (slice 271). | hugrgate |
| `hugrgate.chaos.resources` | 272 | Resource-pressure simulation and guards. Slices 261-262. | hugrgate |
| `hugrgate.chaos.retry` | 150 | Retry budgets: bounded retries for recoverable failures (slice 268). | hugrgate |
| `hugrgate.chaos.scorecard` | 273 | Reliability scorecard: one graded view over experiment reports (slice 27 | hugrgate |
| `hugrgate.chaos.soak` | 195 | Long soak: sustained load + scheduled faults + invariants (slice 273). | hugrgate |
| `hugrgate.circuit` | 174 | Circuit breaker — per-backend failure containment. Slice 18. | hugrgate |
| `hugrgate.cli` | 280 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 220 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.cluster.__init__` | 222 | Cluster package for distributed HugrGate. Campaign IX (slices 201-225). | hugrgate |
| `hugrgate.cluster.auth` | 155 | Mutual authentication for cluster RPC. Slice 208. | hugrgate |
| `hugrgate.cluster.backpressure` | 103 | Backpressure protocol. Slice 218. | hugrgate |
| `hugrgate.cluster.bench` | 304 | Cluster benchmark suite. Slice 224. | hugrgate |
| `hugrgate.cluster.bench_support` | 142 | Loopback cluster harness for benchmarks (and chaos rehearsals). | hugrgate |
| `hugrgate.cluster.capabilities` | 168 | Node capability advertisement. Slice 203. | hugrgate |
| `hugrgate.cluster.chaos` | 138 | Distributed chaos tests. Slice 223. | hugrgate |
| `hugrgate.cluster.discovery` | 175 | Node discovery — finding peers. Slice 204. | hugrgate |
| `hugrgate.cluster.distributed_batch` | 211 | Distributed batching. Slice 217. | hugrgate |
| `hugrgate.cluster.identity` | 123 | Node identity — stable, unforgeable node ids. Slice 202. | hugrgate |
| `hugrgate.cluster.lan` | 286 | LAN discovery adapter — UDP multicast HELLOs. Slice 206. | hugrgate |
| `hugrgate.cluster.node` | 680 | ClusterNode — one HugrGate node in a cluster. Slice 207 (grows). | hugrgate |
| `hugrgate.cluster.node_cost` | 70 | Node cost scoring. Slice 215. | hugrgate |
| `hugrgate.cluster.node_health` | 144 | Node health scoring. Slice 213. | hugrgate |
| `hugrgate.cluster.node_latency` | 133 | Node latency scoring. Slice 214. | hugrgate |
| `hugrgate.cluster.partition` | 98 | Network partition handling. Slice 219. | hugrgate |
| `hugrgate.cluster.policy_sync` | 189 | Policy propagation across the cluster. Slice 210. | hugrgate |
| `hugrgate.cluster.privacy_boundary` | 96 | Privacy boundary enforcement. Slice 211. | hugrgate |
| `hugrgate.cluster.protocol` | 196 | Gjallarbrú node wire protocol. Slice 201. | hugrgate |
| `hugrgate.cluster.provenance_dist` | 139 | Distributed provenance. Slice 221. | hugrgate |
| `hugrgate.cluster.recovery` | 103 | Offline peer recovery. Slice 220. | hugrgate |
| `hugrgate.cluster.release_gate` | 244 | Distributed release gate. Slice 225 (Campaign IX capstone). | hugrgate |
| `hugrgate.cluster.routes` | 99 | Cluster HTTP routes — ``/cluster/*``. Slice 207. | hugrgate |
| `hugrgate.cluster.routing` | 255 | Distributed ladder routing. Slice 212. | hugrgate |
| `hugrgate.cluster.rpc` | 483 | Remote decision RPC. Slice 207. | hugrgate |
| `hugrgate.cluster.static_config` | 182 | Static peer configuration. Slice 205. | hugrgate |
| `hugrgate.cluster.trace` | 247 | Trace correlation. Slice 222. | hugrgate |
| `hugrgate.cluster.transport` | 235 | Encrypted transport for cluster RPC. Slice 209. | hugrgate |
| `hugrgate.cluster.work_stealing` | 127 | Work stealing. Slice 216. | hugrgate |
| `hugrgate.contracts.__init__` | 81 | Decision contracts — versioned, self-describing decision specifications. | hugrgate |
| `hugrgate.contracts.composite` | 188 | Structured composite decisions. Gjallarbrú slice 030. | hugrgate |
| `hugrgate.contracts.composition` | 167 | Contract composition — combining contracts. Gjallarbrú slice 045. | hugrgate |
| `hugrgate.contracts.conditional` | 269 | Conditional decision fields. Gjallarbrú slice 031. | hugrgate |
| `hugrgate.contracts.context` | 275 | Context schemas — typed contracts for decision context. | hugrgate |
| `hugrgate.contracts.cost` | 257 | Cost-sensitive decisions — when mistakes have different prices. | hugrgate |
| `hugrgate.contracts.crossfield` | 289 | Cross-field constraints — invariants over whole decisions. | hugrgate |
| `hugrgate.contracts.deadlines` | 209 | Decision deadlines — temporal bounds on decisions. Gjallarbrú slice 040. | hugrgate |
| `hugrgate.contracts.distributions` | 321 | Distribution constraints — what a healthy distribution looks like. | hugrgate |
| `hugrgate.contracts.explanations` | 228 | Output explanation contracts — decisions must show their work. | hugrgate |
| `hugrgate.contracts.features` | 289 | Input feature contracts — what the model may assume. | hugrgate |
| `hugrgate.contracts.fuzz` | 340 | Contract fuzzing — seeded random contracts, invariant checking. | hugrgate |
| `hugrgate.contracts.hierarchy` | 371 | Hierarchical labels — label forests with ancestor semantics. | hugrgate |
| `hugrgate.contracts.inheritance` | 377 | Contract inheritance — derive, specialize, and check compatibility. | hugrgate |
| `hugrgate.contracts.lint` | 346 | Contract linting — static checks with severities. | hugrgate |
| `hugrgate.contracts.migration` | 239 | Contract migration engine — v1 DecisionSpec ↔ v2 contracts. | hugrgate |
| `hugrgate.contracts.multilabel` | 270 | Multilabel cardinality constraints — how many, which, with what. | hugrgate |
| `hugrgate.contracts.negotiation` | 212 | Contract version negotiation. Gjallarbrú slice 027. | hugrgate |
| `hugrgate.contracts.nested` | 196 | Nested categorical contracts — decision trees. Gjallarbrú slice 028. | hugrgate |
| `hugrgate.contracts.ordinal` | 195 | Rich ordinal semantics — ordinals you can measure. Gjallarbrú slice 033. | hugrgate |
| `hugrgate.contracts.risk` | 242 | Risk matrices — deciding under risk aversion. Gjallarbrú slice 039. | hugrgate |
| `hugrgate.contracts.schema` | 242 | Decision contract schema v2. Gjallarbrú slice 026. | hugrgate |
| `hugrgate.contracts.templates` | 331 | Contract templates — reusable parameterized contracts. | hugrgate |
| `hugrgate.contracts.uncertainty` | 233 | Numeric uncertainty intervals. Gjallarbrú slice 034. | hugrgate |
| `hugrgate.contracts.utility` | 274 | Utility matrices — decisions as gains, not just losses. | hugrgate |
| `hugrgate.core` | 325 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 502 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.edge.__init__` | 269 | Edge Intelligence runtime — Campaign VIII (slices 176-200). | hugrgate |
| `hugrgate.edge.affinity` | 232 | CPU affinity controls for edge inference. Slice 179. | hugrgate |
| `hugrgate.edge.bench` | 458 | Edge benchmark harness and platform suites. Slices 196-198. | hugrgate |
| `hugrgate.edge.bootstrap` | 294 | Offline-first bootstrap for edge deployment. Slice 192. | hugrgate |
| `hugrgate.edge.cachetune` | 157 | Edge-tuned decision cache sizing. Slice 190. | hugrgate |
| `hugrgate.edge.chaos` | 304 | Edge failure testing — deterministic fault injection. Slice 199; | hugrgate |
| `hugrgate.edge.gate` | 258 | Edge Intelligence release gate. Slice 200. | hugrgate |
| `hugrgate.edge.memory` | 210 | Low-RAM operating modes for edge deployment. Slice 178. | hugrgate |
| `hugrgate.edge.npu` | 507 | NPU capability abstraction and vendor adapter boundaries. | hugrgate |
| `hugrgate.edge.platform` | 472 | Edge platform detection, ARM64 audit, and Raspberry Pi baselines. | — |
| `hugrgate.edge.power` | 152 | Power-budget routing for edge deployment. Slice 181. | hugrgate |
| `hugrgate.edge.quant` | 577 | Quantized-model profiles and simulated quantization paths. Slices 182-18 | hugrgate |
| `hugrgate.edge.recovery` | 212 | Intermittent-power recovery via checkpoint journal. Slice 193. | hugrgate |
| `hugrgate.edge.residency` | 199 | Edge model residency management. Slice 189. | hugrgate |
| `hugrgate.edge.routing` | 146 | Edge-aware backend routing. Slices 180-181. | hugrgate |
| `hugrgate.edge.storage` | 305 | Flash-wear-aware storage for edge devices. Slice 191. | hugrgate |
| `hugrgate.edge.telemetry` | 174 | Edge telemetry lite — bounded, privacy-safe metrics. Slice 195. | hugrgate |
| `hugrgate.edge.thermal` | 182 | Thermal sensing and thermal-aware derating. Slice 180. | — |
| `hugrgate.edge.watchdog` | 164 | Edge watchdog — heartbeat supervision for the edge runtime. Slice 194. | hugrgate |
| `hugrgate.ensemble.__init__` | 231 | Ensemble intelligence — one decision from many backends. Slices 101-125. | hugrgate |
| `hugrgate.ensemble.adversarial` | 230 | Ensemble adversarial tests — kick the council and see. Slice 123. | hugrgate |
| `hugrgate.ensemble.api` | 269 | Ensemble API — one decision from many backends. Slice 101. | hugrgate |
| `hugrgate.ensemble.averaging` | 193 | Bayesian model averaging adapter. Slice 106. | hugrgate |
| `hugrgate.ensemble.base` | 330 | Ensemble foundations — shared vote plumbing. Slice 101. | hugrgate |
| `hugrgate.ensemble.batch` | 163 | Ensemble batch mode — one council session, many rulings. Slice 122. | hugrgate |
| `hugrgate.ensemble.benchmarks` | 209 | Ensemble benchmarks — measured, not promised. Slice 125 needs these | hugrgate |
| `hugrgate.ensemble.blending` | 222 | Blending engine — convex member weights from holdout data. Slice 108. | hugrgate |
| `hugrgate.ensemble.cache` | 166 | Ensemble cache — don't re-ask the council. Slice 121. | hugrgate |
| `hugrgate.ensemble.calibration` | 213 | Ensemble calibration — honest probabilities out. Slice 118. | hugrgate |
| `hugrgate.ensemble.consensus` | 135 | Consensus thresholds — supermajority gates. Slice 113. | hugrgate |
| `hugrgate.ensemble.correlation` | 138 | Correlated-error detection — finding members that fail as one. Slice 115 | hugrgate |
| `hugrgate.ensemble.disagreement` | 296 | Disagreement detection, escalation, and minority reports. Slices 111-112 | hugrgate |
| `hugrgate.ensemble.diversity` | 181 | Diversity metrics — measuring *useful* disagreement. Slice 110. | hugrgate |
| `hugrgate.ensemble.explanations` | 167 | Ensemble explanations — the council's reasoning in plain words. Slice 12 | hugrgate |
| `hugrgate.ensemble.membership` | 182 | Dynamic ensemble membership — earn your seat. Slice 117. | hugrgate |
| `hugrgate.ensemble.moe` | 250 | Mixture-of-experts router — route by input region. Slice 109. | hugrgate |
| `hugrgate.ensemble.provenance` | 88 | Ensemble provenance — every council ruling on the record. Slice 119. | hugrgate |
| `hugrgate.ensemble.release` | 263 | Ensemble release gate — the council earns its deployment. Slice 125. | hugrgate |
| `hugrgate.ensemble.reliability` | 137 | Backend reliability weighting — trust, but verify. Slice 116. | hugrgate |
| `hugrgate.ensemble.stacking` | 259 | Stacking engine — a meta-learner over member predictions. Slice 107. | hugrgate |
| `hugrgate.ensemble.voting` | 257 | Voting combiners — many ballots, one decision. Slices 101-105. | hugrgate |
| `hugrgate.errors` | 526 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
| `hugrgate.evlab.__init__` | 276 | Evaluation Laboratory — Gjallarbrú Campaign XV (slices 351-375). | hugrgate |
| `hugrgate.evlab.api` | 485 | Evaluation API v2 — experiments, runs, and run records. Slice 351. | hugrgate |
| `hugrgate.evlab.artifacts` | 249 | Artifact bundles — portable evaluation packages. Slice 371. | hugrgate |
| `hugrgate.evlab.bootstrap` | 305 | Bootstrap confidence intervals for evaluation metrics. Slice 358. | hugrgate |
| `hugrgate.evlab.calibration` | 429 | Calibration-method comparisons — which calibrator helps, where. Slice 36 | hugrgate |
| `hugrgate.evlab.compare` | 248 | Paired backend comparisons — A vs B on identical items. Slice 360. | hugrgate |
| `hugrgate.evlab.costaware` | 247 | Cost-aware evaluation — decision quality per unit spend. Slice 363. | hugrgate |
| `hugrgate.evlab.crossval` | 201 | Cross-validation harness — k-fold evaluation over backends. Slice 357. | hugrgate |
| `hugrgate.evlab.dataset` | 795 | Dataset manifests, versioning, and provenance. Slices 352-354. | hugrgate |
| `hugrgate.evlab.energy` | 233 | Energy-aware evaluation — decision quality per joule. Slice 365. | hugrgate |
| `hugrgate.evlab.fairness` | 234 | Fairness hooks — disparity measurement across groups. Slice 369. | hugrgate |
| `hugrgate.evlab.gates` | 211 | CI quality gates — declarative pass/fail over results. Slice 373. | hugrgate |
| `hugrgate.evlab.history` | 307 | Regression history — run records over time. Slice 370. | hugrgate |
| `hugrgate.evlab.latency` | 182 | Latency-aware evaluation — quality under time pressure. Slice 364. | hugrgate |
| `hugrgate.evlab.privacy` | 281 | Privacy-aware evaluation — the utility cost of privacy. Slice 366. | hugrgate |
| `hugrgate.evlab.release` | 219 | Release gate — the lab's final verdict. Slice 375. | hugrgate |
| `hugrgate.evlab.report` | 288 | Public report generator — the lab's story in Markdown. Slice 374. | hugrgate |
| `hugrgate.evlab.repro` | 225 | Reproducibility manifests — replay recipes. Slice 372. | hugrgate |
| `hugrgate.evlab.robustness` | 266 | Robustness evaluation — quality under perturbation. Slice 367. | hugrgate |
| `hugrgate.evlab.selective` | 333 | Selective-risk evaluation — risk-coverage curves per backend. Slice 362. | hugrgate |
| `hugrgate.evlab.shift` | 274 | Shift evaluation — quality under distribution shift. Slice 368. | hugrgate |
| `hugrgate.evlab.significance` | 281 | Significance testing for paired evaluation outcomes. Slice 359. | hugrgate |
| `hugrgate.evlab.splits` | 241 | Dataset split tooling — train/val/test, stratified, k-fold. Slice 355. | hugrgate |
| `hugrgate.evlab.stratified` | 242 | Stratified evaluation — per-stratum metrics + aggregates. Slice 356. | hugrgate |
| `hugrgate.fallback` | 171 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 291 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.flame` | 268 | Flamegraphs from decision profiles. Slice 277. | hugrgate |
| `hugrgate.gpusched` | 266 | GPU scheduling boundary — discovery, parsing, device assignment. | hugrgate |
| `hugrgate.health` | 140 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.hotpaths` | 169 | Hot-path inventory — ranked cost centers across profiled runs. Slice 278 | hugrgate |
| `hugrgate.ladder` | 520 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.lockaudit` | 262 | Lock contention audit — instrumented locks and static lock-site audit. | hugrgate |
| `hugrgate.log` | 101 | Structured logging for HugrGate (slice 009). | — |
| `hugrgate.millionbench` | 162 | Million-decision benchmark — sustained decision throughput. Slice 299. | hugrgate |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.multiproc` | 256 | Multiprocess execution mode — process pools for CPU-bound fan-out. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.numa` | 247 | NUMA awareness boundary — topology detection and thread pinning. | hugrgate |
| `hugrgate.perfgate` | 280 | Performance regression gates — measure, compare, fail loudly. | hugrgate |
| `hugrgate.policy` | 101 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.pool` | 309 | Connection pooling — generic resource pool + shared HTTP pool. Slice 290 | hugrgate |
| `hugrgate.privacy` | 416 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.privacy_audit` | 151 | Policy violation audit log. Slice 244. | hugrgate |
| `hugrgate.privacy_crypto` | 247 | Authenticated encryption (stdlib only) + encrypted cache. Slice 241. | hugrgate |
| `hugrgate.privacy_deletion` | 202 | Secure deletion hooks. Slice 240. | hugrgate |
| `hugrgate.privacy_dryrun` | 172 | Privacy dry-run mode. Slice 245. | hugrgate |
| `hugrgate.privacy_exfil` | 268 | Exfiltration simulation. Slice 248. | hugrgate |
| `hugrgate.privacy_explain` | 207 | Privacy explanation reports. Slice 246. | hugrgate |
| `hugrgate.privacy_flow` | 206 | Data-flow policy engine. Slice 228. | hugrgate |
| `hugrgate.privacy_jurisdiction` | 128 | Jurisdiction metadata. Slice 230. | hugrgate |
| `hugrgate.privacy_keys` | 254 | Key-provider abstraction. Slice 243. | hugrgate |
| `hugrgate.privacy_labels` | 190 | Field-level sensitivity labels. Slice 227. | — |
| `hugrgate.privacy_localonly` | 129 | Local-only field enforcement. Slice 231. | hugrgate |
| `hugrgate.privacy_minimize` | 185 | Prompt / data minimization. Slice 236. | — |
| `hugrgate.privacy_payload` | 270 | Remote payload compiler — the outbound chokepoint. Slice 237. | hugrgate |
| `hugrgate.privacy_pii` | 246 | PII detector interface. Slice 235. | — |
| `hugrgate.privacy_provenance` | 261 | Privacy-preserving provenance. Slice 238. | hugrgate |
| `hugrgate.privacy_redact` | 320 | Redaction pipeline v2. Slice 232. | hugrgate |
| `hugrgate.privacy_retention` | 118 | Retention policies. Slice 239. | hugrgate |
| `hugrgate.privacy_secrets` | 199 | Secret detection hooks. Slice 234. | hugrgate |
| `hugrgate.privacy_tokens` | 122 | Tokenization / pseudonymization vault. Slice 233. | — |
| `hugrgate.privacy_trust` | 169 | Backend trust levels. Slice 229. | hugrgate |
| `hugrgate.profiling` | 284 | Decision profiler — cProfile integration for the decide() path. Slice 27 | hugrgate |
| `hugrgate.provenance` | 239 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 82 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.routing.__init__` | 211 | Ladder II — intelligence routing subsystem (Campaign III). | hugrgate |
| `hugrgate.routing.architecture` | 404 | Router architecture v2 — plan/execute separation. Slice 051. | hugrgate |
| `hugrgate.routing.availability` | 140 | Availability-aware routing. Slice 062. | hugrgate |
| `hugrgate.routing.capability` | 148 | Capability scoring. Slice 054. | hugrgate |
| `hugrgate.routing.confidence` | 141 | Confidence-aware routing. Slice 055. | hugrgate |
| `hugrgate.routing.cost` | 129 | Cost-aware routing. Slice 057. | hugrgate |
| `hugrgate.routing.dag` | 299 | Conditional routing DAGs. Slice 068. | hugrgate |
| `hugrgate.routing.dsl` | 319 | Route policy DSL. Slice 072. | hugrgate |
| `hugrgate.routing.early_exit` | 184 | Early-exit routing. Slice 066. | hugrgate |
| `hugrgate.routing.energy` | 171 | Energy-aware routing. Slice 058. | hugrgate |
| `hugrgate.routing.explain` | 125 | Route explanation. Slice 069. | hugrgate |
| `hugrgate.routing.fallback` | 239 | Fallback graph routing. Slice 067. | hugrgate |
| `hugrgate.routing.fuzz` | 263 | Routing fuzz tests. Slice 073. | hugrgate |
| `hugrgate.routing.hardware` | 135 | Hardware-aware routing. Slice 061. | hugrgate |
| `hugrgate.routing.hedged` | 212 | Hedged inference. Slice 065. | hugrgate |
| `hugrgate.routing.latency` | 121 | Latency-aware routing. Slice 056. | hugrgate |
| `hugrgate.routing.memory` | 105 | Memory-aware routing. Slice 059. | hugrgate |
| `hugrgate.routing.parallel` | 156 | Parallel speculative rungs. Slice 064. | hugrgate |
| `hugrgate.routing.privacy` | 161 | Privacy-aware routing v2. Slice 060. | hugrgate |
| `hugrgate.routing.qos` | 96 | Quality-of-service classes. Slice 063. | — |
| `hugrgate.routing.replay` | 206 | Route replay. Slice 070. | hugrgate |
| `hugrgate.routing.rungs` | 146 | Dynamic rung construction. Slice 052. | hugrgate |
| `hugrgate.routing.simulate` | 152 | Route simulation. Slice 071. | hugrgate |
| `hugrgate.routing.synthesis` | 112 | Per-request ladder synthesis. Slice 053. | hugrgate |
| `hugrgate.runtimes.__init__` | 540 | Local Model Fabric — runtime interface v2. Slice 151. | hugrgate |
| `hugrgate.runtimes.bench_matrix` | 284 | Local runtime benchmark matrix. Slice 174. | hugrgate |
| `hugrgate.runtimes.conformance` | 394 | Local runtime conformance suite. Slice 173. | hugrgate |
| `hugrgate.runtimes.eviction` | 281 | Model eviction policy. Slice 171. | hugrgate |
| `hugrgate.runtimes.gguf` | 310 | GGUF model discovery. Slice 160. | hugrgate |
| `hugrgate.runtimes.grammar` | 271 | Grammar-constrained decoding. Slice 164. | hugrgate |
| `hugrgate.runtimes.health_probes` | 251 | Model health probes. Slice 172. | hugrgate |
| `hugrgate.runtimes.jsonschema` | 392 | JSON-schema constrained decoding. Slice 165. | hugrgate |
| `hugrgate.runtimes.llama_cpp` | 297 | llama.cpp runtime adapter. Slice 152. | hugrgate |
| `hugrgate.runtimes.metadata` | 330 | Model metadata scanner. Slice 161. | hugrgate |
| `hugrgate.runtimes.mlx` | 254 | MLX adapter boundary. Slice 157. | hugrgate |
| `hugrgate.runtimes.ollama` | 300 | Ollama-compatible runtime adapter. Slice 153. | hugrgate |
| `hugrgate.runtimes.onnx` | 318 | ONNX Runtime adapter. Slice 154. | hugrgate |
| `hugrgate.runtimes.openvino` | 289 | OpenVINO runtime adapter. Slice 158. | hugrgate |
| `hugrgate.runtimes.packs` | 255 | Local model packs. Slices 166-168. | hugrgate |
| `hugrgate.runtimes.probe` | 218 | Model capability probing. Slice 162. | hugrgate |
| `hugrgate.runtimes.residency` | 186 | Model residency manager. Slice 170. | hugrgate |
| `hugrgate.runtimes.session_pool` | 219 | Model-session pooling — warm loaded runtimes, keyed by model. Slice 291. | hugrgate |
| `hugrgate.runtimes.structured` | 468 | Structured-output adapter. Slice 163. | hugrgate |
| `hugrgate.runtimes.tensorrt` | 452 | TensorRT adapter boundary. Slice 159. | hugrgate |
| `hugrgate.runtimes.transformers_rt` | 376 | Transformers runtime adapter. Slice 155. | hugrgate |
| `hugrgate.runtimes.vllm` | 388 | vLLM local adapter. Slice 156. | hugrgate |
| `hugrgate.runtimes.warmup` | 222 | Model warmup manager. Slice 169. | hugrgate |
| `hugrgate.scheduler` | 633 | Batch scheduler v2 — general-purpose windowed batch engine. Slice 285. | hugrgate |
| `hugrgate.serde` | 205 | JSON serde helpers shared by the server, daemon, CLI and SDK. | hugrgate |
| `hugrgate.server` | 386 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 127 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.supervision` | 302 | Worker supervision — heartbeats, restarts, escalation. Slice 295. | hugrgate |
| `hugrgate.threshold` | 213 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
| `hugrgate.timeout` | 139 | Timeouts — per-decision deadline enforcement via threads. Slice 19. | hugrgate |
| `hugrgate.validation` | 131 | Validation layer — the application never receives an invalid value. Slic | hugrgate |
| `hugrgate.zerocopy` | 345 | Zero-copy result sharing. Slice 280. | hugrgate |

## Findings (forwarded to later slices)

1. `hugrgate/client.py` imports `httpx` at module level, but `httpx` is
   not declared in `pyproject.toml` (only present transitively in the dev
   venv). `hugrgate/cli.py` imports it lazily inside a function.
   → slice 004/008: declare `httpx` in the `server` extra (or make
   `client.py` degrade gracefully when it is absent).
2. `docs/api.md` documents the HTTP surface; the Python API has no
   equivalent inventory page. → slice 003.
3. No machine-readable architecture/dependency map existed before this
   audit. → slice 002/004.

## Verification

Re-run `venv/bin/python tools/audit_repo.py` and diff
`docs/campaign-i/manifest.json`; `tests/test_repo_truth.py` encodes
the key invariants so drift fails the suite.
