#!/usr/bin/env python3
"""Architecture map generator for HugrGate (Gjallarbrú slice 002).

Parses every module's AST, records internal ``hugrgate.*`` import edges
(marking imports that happen inside functions as LAZY), assigns each
module to an explicit architectural layer, and writes a deterministic
Markdown map (Mermaid diagram + layer table + edge list) to
``docs/campaign-i/architecture-map.md``.

Deterministic: same tree -> same bytes. Run from the repo root.
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "hugrgate")
OUT = os.path.join(ROOT, "docs", "campaign-i", "architecture-map.md")

# Explicit, auditable layer assignment. Every module must appear here;
# the generator fails loudly on an unmapped module (see slice-002 test).
LAYERS: dict[str, list[str]] = {
    "foundation": ["hugrgate.errors"],
    "contracts": [
        "hugrgate.spec", "hugrgate.result", "hugrgate.backend",
        "hugrgate.policy", "hugrgate.validation", "hugrgate.serde",
    ],
    "contract-engine": [
        "hugrgate.contracts", "hugrgate.contracts.schema",
        "hugrgate.contracts.negotiation",
        "hugrgate.contracts.nested",
        "hugrgate.contracts.hierarchy",
        "hugrgate.contracts.composite",
        "hugrgate.contracts.conditional",
        "hugrgate.contracts.crossfield",
        "hugrgate.contracts.ordinal",
        "hugrgate.contracts.uncertainty",
        "hugrgate.contracts.distributions",
        "hugrgate.contracts.multilabel",
        "hugrgate.contracts.cost",
        "hugrgate.contracts.utility",
        "hugrgate.contracts.risk",
        "hugrgate.contracts.deadlines",
        "hugrgate.contracts.context",
        "hugrgate.contracts.features",
        "hugrgate.contracts.explanations",
        "hugrgate.contracts.inheritance",
        "hugrgate.contracts.composition",
        "hugrgate.contracts.templates",
        "hugrgate.contracts.migration",
        "hugrgate.contracts.lint",
        "hugrgate.contracts.fuzz",
    ],
    "local-runtimes": [
        "hugrgate.runtimes", "hugrgate.runtimes.bench_matrix",
        "hugrgate.runtimes.conformance", "hugrgate.runtimes.eviction",
        "hugrgate.runtimes.gguf", "hugrgate.runtimes.grammar",
        "hugrgate.runtimes.health_probes", "hugrgate.runtimes.jsonschema",
        "hugrgate.runtimes.llama_cpp", "hugrgate.runtimes.metadata",
        "hugrgate.runtimes.mlx", "hugrgate.runtimes.ollama",
        "hugrgate.runtimes.onnx", "hugrgate.runtimes.openvino",
        "hugrgate.runtimes.packs", "hugrgate.runtimes.probe",
        "hugrgate.runtimes.residency", "hugrgate.runtimes.structured",
        "hugrgate.runtimes.tensorrt",
        "hugrgate.runtimes.transformers_rt", "hugrgate.runtimes.vllm",
        "hugrgate.runtimes.warmup", "hugrgate.runtimes.session_pool",
    ],
    "runtime": [
        "hugrgate.core", "hugrgate.abstain", "hugrgate.threshold",
        "hugrgate.negotiate", "hugrgate.fallback", "hugrgate.timeout",
        "hugrgate.circuit", "hugrgate.privacy", "hugrgate.ladder",
    ],
    "privacy-fortress": [  # Campaign X — data sovereignty controls
        "hugrgate.privacy_audit", "hugrgate.privacy_crypto",
        "hugrgate.privacy_deletion", "hugrgate.privacy_dryrun",
        "hugrgate.privacy_exfil", "hugrgate.privacy_explain",
        "hugrgate.privacy_flow", "hugrgate.privacy_jurisdiction",
        "hugrgate.privacy_keys", "hugrgate.privacy_labels",
        "hugrgate.privacy_localonly", "hugrgate.privacy_minimize",
        "hugrgate.privacy_payload", "hugrgate.privacy_pii",
        "hugrgate.privacy_provenance", "hugrgate.privacy_redact",
        "hugrgate.privacy_retention", "hugrgate.privacy_secrets",
        "hugrgate.privacy_tokens", "hugrgate.privacy_trust",
    ],
    "routing": [  # Campaign III — Ladder II plan/execute routing subsystem
        "hugrgate.routing", "hugrgate.routing.architecture",
        "hugrgate.routing.rungs", "hugrgate.routing.synthesis",
        "hugrgate.routing.capability", "hugrgate.routing.confidence",
        "hugrgate.routing.latency", "hugrgate.routing.cost",
        "hugrgate.routing.energy", "hugrgate.routing.memory",
        "hugrgate.routing.privacy", "hugrgate.routing.hardware",
        "hugrgate.routing.availability", "hugrgate.routing.qos",
        "hugrgate.routing.parallel", "hugrgate.routing.hedged",
        "hugrgate.routing.early_exit", "hugrgate.routing.fallback",
        "hugrgate.routing.dag", "hugrgate.routing.explain",
        "hugrgate.routing.replay", "hugrgate.routing.simulate",
        "hugrgate.routing.dsl", "hugrgate.routing.fuzz",
    ],
    "state": [
        "hugrgate.provenance", "hugrgate.health", "hugrgate.drift",
        "hugrgate.cache", "hugrgate.models", "hugrgate.features",
        "hugrgate.bench", "hugrgate.bench_report", "hugrgate.log",
    ],
    "memory": [  # Campaign XIII — decision memory package
        "hugrgate.memory", "hugrgate.memory.access",
        "hugrgate.memory.adversarial",
        "hugrgate.memory.assisted_calibration",
        "hugrgate.memory.assisted_routing",
        "hugrgate.memory.backend_history",
        "hugrgate.memory.benchmarks", "hugrgate.memory.compaction",
        "hugrgate.memory.conditioned",
        "hugrgate.memory.contract_history",
        "hugrgate.memory.counterfactuals", "hugrgate.memory.decay",
        "hugrgate.memory.domain_profiles", "hugrgate.memory.frequency",
        "hugrgate.memory.groundtruth", "hugrgate.memory.history",
        "hugrgate.memory.io", "hugrgate.memory.outcomes",
        "hugrgate.memory.policies", "hugrgate.memory.query",
        "hugrgate.memory.recency", "hugrgate.memory.replay",
        "hugrgate.memory.retention", "hugrgate.memory.retrieval",
        "hugrgate.memory.similarity", "hugrgate.memory.types",
    ],
    "backends": [
        "hugrgate.backends.rules", "hugrgate.backends.logreg",
        "hugrgate.backends.forest", "hugrgate.backends.boosting",
        "hugrgate.backends.embedding", "hugrgate.backends.llm",
        "hugrgate.backends.nli",
    ],
    "calibration": [
        "hugrgate.calibration", "hugrgate.calibration._base",
        "hugrgate.calibration.adversarial",
        "hugrgate.calibration.aleatoric",
        "hugrgate.calibration.autoselect",
        "hugrgate.calibration.bayes",
        "hugrgate.calibration.bench",
        "hugrgate.calibration.conformal",
        "hugrgate.calibration.conformal_regression",
        "hugrgate.calibration.coverage",
        "hugrgate.calibration.decomposition",
        "hugrgate.calibration.drift",
        "hugrgate.calibration.ensemble",
        "hugrgate.calibration.epistemic",
        "hugrgate.calibration.group",
        "hugrgate.calibration.imbalance",
        "hugrgate.calibration.isotonic",
        "hugrgate.calibration.metrics",
        "hugrgate.calibration.online",
        "hugrgate.calibration.perclass",
        "hugrgate.calibration.pipeline",
        "hugrgate.calibration.platt",
        "hugrgate.calibration.profiles",
        "hugrgate.calibration.registry",
        "hugrgate.calibration.risk_coverage",
        "hugrgate.calibration.selective",
        "hugrgate.calibration.sets",
        "hugrgate.calibration.shift",
        "hugrgate.calibration.temperature",
        "hugrgate.calibration.viz",
        "hugrgate.calibration.window",
    ],
    "ensemble": [  # Gjallarbrú campaign V, slices 101-125
        "hugrgate.ensemble", "hugrgate.ensemble.base",
        "hugrgate.ensemble.api", "hugrgate.ensemble.voting",
        "hugrgate.ensemble.averaging", "hugrgate.ensemble.stacking",
        "hugrgate.ensemble.blending", "hugrgate.ensemble.moe",
        "hugrgate.ensemble.diversity", "hugrgate.ensemble.disagreement",
        "hugrgate.ensemble.consensus", "hugrgate.ensemble.correlation",
        "hugrgate.ensemble.reliability", "hugrgate.ensemble.membership",
        "hugrgate.ensemble.calibration", "hugrgate.ensemble.provenance",
        "hugrgate.ensemble.explanations", "hugrgate.ensemble.cache",
        "hugrgate.ensemble.batch", "hugrgate.ensemble.adversarial",
        "hugrgate.ensemble.benchmarks", "hugrgate.ensemble.release",
    ],
    "service": [
        "hugrgate.server", "hugrgate.daemon", "hugrgate.client",
        "hugrgate.cli",
    ],
    "adaptive": [
        "hugrgate.adaptive",
        "hugrgate.adaptive.telemetry",
        "hugrgate.adaptive.feedback",
        "hugrgate.adaptive.delayed",
        "hugrgate.adaptive.router_features",
        "hugrgate.adaptive.bandit",
        "hugrgate.adaptive.offline",
        "hugrgate.adaptive.cost_quality",
        "hugrgate.adaptive.latency_quality",
        "hugrgate.adaptive.energy_quality",
        "hugrgate.adaptive.privacy_objective",
        "hugrgate.adaptive.multiobjective",
        "hugrgate.adaptive.competence",
        "hugrgate.adaptive.domain_competence",
        "hugrgate.adaptive.contract_competence",
        "hugrgate.adaptive.coldstart",
        "hugrgate.adaptive.exploration",
        "hugrgate.adaptive.safe_exploration",
        "hugrgate.adaptive.shadow",
        "hugrgate.adaptive.counterfactual",
        "hugrgate.adaptive.rollback",
        "hugrgate.adaptive.versioning",
        "hugrgate.adaptive.explanations",
        "hugrgate.adaptive.drift_detect",
        "hugrgate.adaptive.benchmark",
    ],
    "cluster": [
        "hugrgate.cluster", "hugrgate.cluster.protocol",
        "hugrgate.cluster.identity",
        "hugrgate.cluster.capabilities",
        "hugrgate.cluster.discovery",
        "hugrgate.cluster.static_config",
        "hugrgate.cluster.lan",
        "hugrgate.cluster.rpc",
        "hugrgate.cluster.node",
        "hugrgate.cluster.routes",
        "hugrgate.cluster.auth",
        "hugrgate.cluster.transport",
        "hugrgate.cluster.policy_sync",
        "hugrgate.cluster.privacy_boundary",
        "hugrgate.cluster.routing",
        "hugrgate.cluster.node_health",
        "hugrgate.cluster.node_latency",
        "hugrgate.cluster.node_cost",
        "hugrgate.cluster.work_stealing",
        "hugrgate.cluster.distributed_batch",
        "hugrgate.cluster.backpressure",
        "hugrgate.cluster.partition",
        "hugrgate.cluster.recovery",
        "hugrgate.cluster.provenance_dist",
        "hugrgate.cluster.trace",
        "hugrgate.cluster.chaos",
        "hugrgate.cluster.bench_support",
        "hugrgate.cluster.bench",
        "hugrgate.cluster.release_gate",
    ],
    "api": ["hugrgate"],
    "performance": [  # Gjallarbrú campaign XII, slices 276-299
        "hugrgate.profiling", "hugrgate.flame", "hugrgate.hotpaths",
        "hugrgate.allocprof", "hugrgate.zerocopy", "hugrgate.asyncx",
        "hugrgate.async_backend", "hugrgate.scheduler",
        "hugrgate.backpressure", "hugrgate.pool", "hugrgate.lockaudit",
        "hugrgate.multiproc", "hugrgate.supervision", "hugrgate.numa",
        "hugrgate.gpusched", "hugrgate.perfgate", "hugrgate.millionbench",
    ],
    "edge": [
        "hugrgate.edge", "hugrgate.edge.platform",
        "hugrgate.edge.memory",
        "hugrgate.edge.affinity",
        "hugrgate.edge.thermal", "hugrgate.edge.routing",
        "hugrgate.edge.power",
        "hugrgate.edge.quant",
        "hugrgate.edge.npu",
        "hugrgate.edge.residency",
        "hugrgate.edge.cachetune",
        "hugrgate.edge.storage",
        "hugrgate.edge.bootstrap",
        "hugrgate.edge.recovery",
        "hugrgate.edge.watchdog",
        "hugrgate.edge.telemetry",
        "hugrgate.edge.bench",
        "hugrgate.edge.chaos",
        "hugrgate.edge.gate",
    ],
    "chaos": [  # Gjallarbrú campaign XI, slices 251-275
        "hugrgate.chaos", "hugrgate.chaos.framework",
        "hugrgate.chaos.backend_faults", "hugrgate.chaos.model_faults",
        "hugrgate.chaos.cache_faults", "hugrgate.chaos.filesystem",
        "hugrgate.chaos.resources", "hugrgate.chaos.network",
        "hugrgate.chaos.clock", "hugrgate.chaos.experiments",
        "hugrgate.chaos.retry", "hugrgate.chaos.bulkhead",
        "hugrgate.chaos.degradation", "hugrgate.chaos.recovery",
        "hugrgate.chaos.crash", "hugrgate.chaos.soak",
        "hugrgate.chaos.scorecard",
    ],
    "observability": [  # Gjallarbrú campaign XIV, slices 326-350
        "hugrgate.observability",
        "hugrgate.observability.metrics",
        "hugrgate.observability.otel",
        "hugrgate.observability.trace",
        "hugrgate.observability.spans_decision",
        "hugrgate.observability.spans_backend",
        "hugrgate.observability.spans_routing",
        "hugrgate.observability.spans_calibration",
        "hugrgate.observability.logschema",
        "hugrgate.observability.prometheus",
        "hugrgate.observability.dashboard",
        "hugrgate.observability.histograms",
        "hugrgate.observability.confidence",
        "hugrgate.observability.abstention",
        "hugrgate.observability.escalation",
        "hugrgate.observability.cost",
        "hugrgate.observability.energy",
        "hugrgate.observability.privacy_metrics",
        "hugrgate.observability.alerts",
        "hugrgate.observability.slo",
        "hugrgate.observability.slo_eval",
        "hugrgate.observability.explain",
        "hugrgate.observability.replay",
        "hugrgate.observability.load",
    ],
}

LAYER_OF = {m: layer for layer, mods in LAYERS.items() for m in mods}


class EdgeVisitor(ast.NodeVisitor):
    """Collect internal imports; flag those nested inside functions."""

    def __init__(self) -> None:
        self.edges: dict[str, bool] = {}  # target -> is_lazy
        self._depth = 0

    def visit_FunctionDef(self, node):
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record(self, module: str | None) -> None:
        if module and module.startswith("hugrgate"):
            lazy = self._depth > 0
            self.edges[module] = self.edges.get(module, False) or lazy
            # keep the eager bit if ANY import site is eager
            if not lazy:
                self.edges[module] = False

    def visit_Import(self, node):
        for a in node.names:
            if a.name.startswith("hugrgate"):
                self._record(a.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.startswith("hugrgate"):
            self._record(node.module)
        self.generic_visit(node)


def resolve(dep: str, modules: set[str]) -> str | None:
    while dep not in modules and "." in dep:
        dep = dep.rsplit(".", 1)[0]
    return dep if dep in modules else None


def _scan_modules(pkg_dir: str = PKG) -> dict[str, dict]:
    """Parse every module under *pkg_dir*; returns mod -> {path, edges}."""
    modules: dict[str, dict] = {}
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
            mod = rel[: -len(".__init__")] if rel.endswith(".__init__") else rel
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            visitor = EdgeVisitor()
            visitor.visit(tree)
            modules[mod] = {"path": path, "edges": visitor.edges}
    return modules


# Backwards-compatible alias used by tests.
def _walk_for_tests() -> dict[str, dict]:
    return _scan_modules()


def _unmapped(modules: dict[str, dict]) -> list[str]:
    """Modules with no explicit layer assignment."""
    return sorted(set(modules) - set(LAYER_OF))


def main() -> int:
    modules = _scan_modules()

    unmapped = _unmapped(modules)
    if unmapped:
        print(f"ERROR: unmapped modules: {unmapped}", file=sys.stderr)
        return 1

    names = set(modules)
    edges: dict[str, dict[str, bool]] = {}
    for mod, info in modules.items():
        resolved: dict[str, bool] = {}
        for target, lazy in info["edges"].items():
            r = resolve(target, names)
            if r and r != mod:
                resolved[r] = resolved.get(r, True) and lazy
        edges[mod] = resolved

    short = lambda m: m.replace("hugrgate.", "")  # noqa: E731

    lines = [
        "# HugrGate architecture map",
        "",
        "Generated by `tools/gen_arch_map.py` (slice 002). Deterministic:",
        "re-running the generator on an unchanged tree yields byte-identical",
        "output. Edges marked `(lazy)` are imports deferred inside functions",
        "rather than at module top level.",
        "",
        "## Layers",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    for layer, mods in LAYERS.items():
        node_ids = [short(m).replace(".", "_") for m in mods]
        lines.append(f"    subgraph {layer}[{layer}]")
        for m, nid in zip(mods, node_ids, strict=True):
            lines.append(f"        {nid}[{short(m)}]")
        lines.append("    end")
    lines.append("")
    for mod in sorted(edges):
        src = short(mod).replace(".", "_")
        for tgt in sorted(edges[mod]):
            dst = short(tgt).replace(".", "_")
            style = " -.-> " if edges[mod][tgt] else " --> "
            lines.append(f"    {src}{style}{dst}")
    lines += [
        "```",
        "",
        "## Layer membership",
        "",
        "| Layer | Modules |",
        "|---|---|",
    ]
    for layer, mods in LAYERS.items():
        lines.append(f"| {layer} | {', '.join(f'`{short(m)}`' for m in mods)} |")
    lines += [
        "",
        "## Internal dependency edges",
        "",
        "| From | To | Lazy |",
        "|---|---|---|---|",
    ]
    for mod in sorted(edges):
        for tgt in sorted(edges[mod]):
            lazy = "yes" if edges[mod][tgt] else "no"
            lines.append(f"| `{short(mod)}` | `{short(tgt)}` | {lazy} |")
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {OUT} ({sum(len(e) for e in edges.values())} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
