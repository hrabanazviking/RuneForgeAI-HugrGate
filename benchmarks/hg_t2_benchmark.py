"""HG-T2 benchmark — rules-only vs selective model path.

Runs the frozen case set (benchmarks/hg_t2_cases.py) three ways:

1. rules-only (KeywordBackend) — accuracy + median latency;
2. per candidate Ollama model: the SelectiveModelBackend — accuracy,
   median latency, and the model-invocation count (the selective gate
   must fire on the hard cases and NOT on the clear ones);
3. the pick: highest selective accuracy, then lowest median latency
   on model-invoked cases. The pick and every number are written to
   campaign/hg_t2_benchmark_report.json — the gate evidence.

Usage: python3 benchmarks/hg_t2_benchmark.py [model ...]
Default candidates: gemma4viking4b:latest, b1olmoe:latest.
A candidate whose endpoint/model fails is recorded as unavailable
with its error — never silently dropped, never faked.
Warmup calls (one per candidate) are excluded from latency numbers.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hg_t2_cases import CASES, SPEC  # noqa: E402

from hugrgate.decision_server import KeywordBackend  # noqa: E402
from hugrgate.model_backend import (  # noqa: E402
    OllamaEngine,
    SelectiveModelBackend,
    build_model_backend,
)
from hugrgate.spec import DecisionSpec  # noqa: E402

REPORT = (Path(__file__).resolve().parent.parent
          / "campaign" / "hg_t2_benchmark_report.json")
DEFAULT_CANDIDATES = ["gemma4viking4b:latest", "b1olmoe:latest"]


def _run(backend, cases):
    spec = DecisionSpec.from_dict(dict(SPEC))
    rows, lat = [], []
    for case in cases:
        t0 = time.perf_counter()
        result = backend.evaluate({"text": case["text"]}, spec)
        lat.append((time.perf_counter() - t0) * 1000.0)
        rows.append({"id": case["id"], "kind": case["kind"],
                     "expected": case["expected"],
                     "got": result.value,
                     "correct": result.value == case["expected"],
                     "route": result.metadata.get("route"),
                     "model_used": bool(
                         result.metadata.get("model_used")),
                     "latency_ms": round(lat[-1], 3)})
    return rows, lat


def _summarize(rows, lat):
    def acc(kind):
        sel = [r for r in rows if kind is None or r["kind"] == kind]
        return round(sum(r["correct"] for r in sel) / len(sel), 4)
    return {"n": len(rows), "accuracy": acc(None),
            "accuracy_clear": acc("clear"),
            "accuracy_hard": acc("hard"),
            "median_latency_ms": round(statistics.median(lat), 3),
            "model_invocations": sum(r["model_used"] for r in rows),
            "rows": rows}


def main(argv):
    candidates = argv[1:] or DEFAULT_CANDIDATES
    report = {"slice": "HG-T2", "case_set": "benchmarks/hg_t2_cases.py",
              "n_cases": len(CASES),
              "spec": SPEC, "candidates": candidates}
    rules_rows, rules_lat = _run(KeywordBackend(), CASES)
    report["rules_only"] = _summarize(rules_rows, rules_lat)
    print(f"rules-only: acc={report['rules_only']['accuracy']} "
          f"clear={report['rules_only']['accuracy_clear']} "
          f"hard={report['rules_only']['accuracy_hard']} "
          f"median={report['rules_only']['median_latency_ms']}ms")
    report["models"] = {}
    for model in candidates:
        entry = {}
        try:
            engine = OllamaEngine(model=model)
            health = engine.health()
            entry["health"] = health
            if health.get("status") != "ok" or \
                    not health.get("model_present"):
                entry["status"] = "unavailable"
                report["models"][model] = entry
                print(f"{model}: unavailable {health}")
                continue
            backend = SelectiveModelBackend(
                model_backend=build_model_backend(model=model))
            # Warmup (model load) — excluded from all numbers.
            t0 = time.perf_counter()
            backend.evaluate({"text": "warmup ping"},
                             DecisionSpec.from_dict(dict(SPEC)))
            entry["warmup_ms"] = round(
                (time.perf_counter() - t0) * 1000.0, 1)
            rows, lat = _run(backend, CASES)
            entry.update(_summarize(rows, lat))
            invoked = [r for r in rows if r["model_used"]]
            entry["model_median_latency_ms"] = round(
                statistics.median([r["latency_ms"] for r in invoked]),
                1) if invoked else None
            entry["status"] = "ok"
            print(f"{model}: acc={entry['accuracy']} "
                  f"hard={entry['accuracy_hard']} "
                  f"invoked={entry['model_invocations']} "
                  f"model_median={entry['model_median_latency_ms']}ms "
                  f"warmup={entry['warmup_ms']}ms")
        except Exception as e:  # noqa: BLE001 - recorded, not hidden
            entry["status"] = "error"
            entry["error"] = f"{type(e).__name__}: {e}"
            print(f"{model}: ERROR {entry['error']}")
        report["models"][model] = entry
    ok = {m: e for m, e in report["models"].items()
          if e.get("status") == "ok"}
    if ok:
        pick = sorted(ok.items(), key=lambda kv: (
            -kv[1]["accuracy"],
            kv[1]["model_median_latency_ms"] or 1e18))[0][0]
        report["pick"] = pick
        report["pick_reason"] = (
            "highest selective accuracy on the frozen case set, "
            "then lowest median model latency")
    else:
        report["pick"] = None
        report["pick_reason"] = "no candidate model was available"
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"pick: {report['pick']} — report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
