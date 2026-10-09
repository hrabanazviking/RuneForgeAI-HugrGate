# Slice 023 — Test taxonomy rebuild

**Date:** 2026-10-09 · **Tests:** `tests/test_taxonomy.py` (3 tests)

## What the audit found

27 test files with no shared fixtures (every file redefined its own
stub backends and specs), no markers (no way to run "fast tests
only"), and no statement of what each file is *for*. The taxonomy is
now explicit and enforced.

## The taxonomy

| Category | Marker | Meaning | Files |
|---|---|---|---|
| unit | *(none)* | fast, single-component, no I/O | test_config, test_errors, test_foundation, test_logging, test_policy_invariants, test_provenance_integrity, test_resource_lifecycle, test_result_invariants, test_serialization_contracts, test_state_validation, test_backend_registry, test_coverage_attack, test_cluster_protocol, test_cluster_identity, test_cluster_capabilities, test_cluster_discovery, test_cluster_static_config, test_cluster_rpc, test_cluster_auth, test_cluster_policy_sync, test_cluster_privacy_boundary, test_cluster_routing, test_cluster_node_health, test_cluster_node_latency, test_cluster_node_cost, test_cluster_work_stealing, test_cluster_distributed_batch, test_cluster_backpressure, test_cluster_partition, test_cluster_recovery, test_cluster_provenance_dist, test_cluster_trace, test_cluster_chaos, test_cluster_bench, test_cluster_release_gate , test_adaptive_bandit, test_adaptive_benchmark, test_adaptive_coldstart, test_adaptive_competence, test_adaptive_contract_competence, test_adaptive_cost_quality, test_adaptive_counterfactual, test_adaptive_delayed, test_adaptive_domain_competence, test_adaptive_drift, test_adaptive_energy_quality, test_adaptive_explanations, test_adaptive_exploration, test_adaptive_feedback, test_adaptive_latency_quality, test_adaptive_multiobjective, test_adaptive_offline, test_adaptive_privacy_objective, test_adaptive_rollback, test_adaptive_router_features, test_adaptive_safe_exploration, test_adaptive_shadow, test_adaptive_telemetry, test_adaptive_versioning, test_calib_adversarial, test_calib_aleatoric, test_calib_autoselect, test_calib_bayes, test_calib_bench, test_calib_conformal, test_calib_conformal_reg, test_calib_coverage, test_calib_decomposition, test_calib_drift, test_calib_ensemble, test_calib_epistemic, test_calib_group, test_calib_imbalance, test_calib_online, test_calib_perclass, test_calib_pipeline, test_calib_registry, test_calib_risk_coverage, test_calib_selective, test_calib_sets, test_calib_shift, test_calib_viz, test_calib_window, test_contracts_026, test_contracts_027, test_contracts_028, test_contracts_029, test_contracts_030, test_contracts_031, test_contracts_032, test_contracts_033, test_contracts_034, test_contracts_035, test_contracts_036, test_contracts_037, test_contracts_038, test_contracts_039, test_contracts_040, test_contracts_041, test_contracts_042, test_contracts_043, test_contracts_044, test_contracts_045, test_contracts_046, test_contracts_047, test_contracts_048, test_contracts_049, test_contracts_050, test_edge_affinity, test_edge_bench, test_edge_bootstrap, test_edge_cachetune, test_edge_chaos, test_chaos_framework, test_edge_gate, test_edge_memory, test_edge_npu, test_edge_platform, test_edge_power, test_edge_quant, test_edge_recovery, test_edge_residency, test_edge_storage, test_edge_telemetry, test_edge_thermal, test_edge_watchdog, test_ensemble_101_api, test_ensemble_102_hard_voting, test_ensemble_103_soft_voting, test_ensemble_104_weighted_voting, test_ensemble_105_confidence_voting, test_ensemble_106_bma, test_ensemble_107_stacking, test_ensemble_108_blending, test_ensemble_109_moe, test_ensemble_110_diversity, test_ensemble_111_disagreement, test_ensemble_112_escalation, test_ensemble_113_consensus, test_ensemble_114_minority, test_ensemble_115_correlation, test_ensemble_116_reliability, test_ensemble_117_membership, test_ensemble_118_calibration, test_ensemble_119_provenance, test_ensemble_120_explanations, test_ensemble_121_caching, test_ensemble_122_batch, test_ensemble_123_adversarial, test_ensemble_124_benchmarks, test_ensemble_125_release, test_localrt_151_interface, test_localrt_152_llamacpp, test_localrt_153_ollama, test_localrt_154_onnx, test_localrt_155_transformers, test_localrt_156_vllm, test_localrt_157_mlx, test_localrt_158_openvino, test_localrt_159_tensorrt, test_localrt_160_gguf, test_localrt_161_metadata, test_localrt_162_probe, test_localrt_163_structured, test_localrt_164_grammar, test_localrt_165_jsonschema, test_localrt_166_nli_packs, test_localrt_167_embedding_packs, test_localrt_168_classifier_packs, test_localrt_169_warmup, test_localrt_170_residency, test_localrt_171_eviction, test_localrt_172_health_probes, test_localrt_173_conformance, test_localrt_174_bench_matrix, test_routing_051, test_routing_052, test_routing_053, test_routing_054, test_routing_055, test_routing_056, test_routing_057, test_routing_058, test_routing_059, test_routing_060, test_routing_061, test_routing_062, test_routing_063, test_routing_064, test_routing_065, test_routing_066, test_routing_067, test_routing_068, test_routing_069, test_routing_070, test_routing_071, test_routing_072, test_routing_073, test_routing_074 |
| integration | `pytest.mark.integration` | multi-component behavior | test_ladder, test_deterministic, test_ml_calibration |
| slow | `pytest.mark.slow` | spawns servers/threads, sleeps | test_service, test_thread_safety, test_async_readiness, test_cluster_lan, test_cluster_transport |
| gate | `pytest.mark.gate` | meta-tests shelling out to tools | test_typecheck, test_static_analysis, test_arch_map, test_api_inventory, test_repo_truth, test_dependency_rules, test_import_cycles, test_package_boundaries, test_dead_code, test_determinism_contract, test_taxonomy, test_release_gate |

(`test_package_boundaries` is a gate: it runs a subprocess import
sweep. Unit is the default — no marker required.)

Useful selections: `pytest -m "not slow and not gate"` (378 fast
tests), `pytest -m gate` (58 tool-gate tests).

## Changes

- `tests/conftest.py`: shared fixtures — `cat_spec`, `binary_spec`,
  `policy`, `strict_policy`, `StubBackend` (deterministic,
  distribution-consistent), `stub_backend`, `gate_with_stub`.
- Markers registered in `[tool.pytest.ini_options]`; `pytestmark`
  applied per file per the table.
- `tests/test_taxonomy.py`: enforcement — every test module must
  carry a known category marker or be listed as unit in this doc's
  table; marked files must carry the matching `pytestmark`.

## Verification

Enforcement tests green; `ruff check` clean; collection works under
`-m` selections; full suite green.
