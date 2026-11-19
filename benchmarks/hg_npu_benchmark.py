"""HG-NPU benchmark — re-earn the judge pick on the XDNA2 NPU.

Runs the frozen HG-T2 case set (benchmarks/hg_t2_cases.py, never
altered) through the SelectiveModelBackend wired to FastFlowLM
(``flm serve``) on the deployment host's NPU, per candidate model:

1. rules-only (KeywordBackend) — re-measured reference;
2. per candidate FLM model: selective accuracy (overall / clear /
   hard), model-invocation count, cold first-call latency (first
   judgment after serve start, warmup excluded from warm numbers),
   warm model latency (median over repeated hard-case passes), and
   the flm process footprint (VmRSS, idle-loaded and post-run);
3. the pick: highest selective accuracy, then lowest warm model
   latency — the HG-T2 rule, unchanged. The incumbent GPU pick's
   frozen numbers (campaign/hg_t2_benchmark_report.json) are copied
   into the report for comparison; if no candidate matches the
   incumbent's accuracy, the report says so plainly.

A candidate that cannot be served (not pulled, no FLM build, serve
failure) is recorded as unavailable with its error — never silently
dropped, never faked.

Usage (on the NPU host, inside a context with raised memlock —
flm refuses the default 8 MiB):
  systemd-run --user -p LimitMEMLOCK=infinity --wait \
      python3 benchmarks/hg_npu_benchmark.py [model ...]
Default candidates: qwen3:0.6b d3:lite qwen3:1.7b gemma3:1b
                    gemma4-it:e2b phi4-mini
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hg_t2_cases import CASES, SPEC  # noqa: E402

from hugrgate.decision_server import KeywordBackend  # noqa: E402
from hugrgate.flm_backend import FlmEngine, build_flm_backend  # noqa: E402
from hugrgate.model_backend import SelectiveModelBackend  # noqa: E402
from hugrgate.spec import DecisionSpec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "campaign" / "hg_npu_benchmark_report.json"
INCUMBENT_REPORT = ROOT / "campaign" / "hg_t2_benchmark_report.json"
FLM_PORT = 52625
FLM_BASE = f"http://127.0.0.1:{FLM_PORT}"
DEFAULT_CANDIDATES = ["qwen3:0.6b", "d3:lite", "qwen3:1.7b",
                      "gemma3:1b", "gemma4-it:e2b", "phi4-mini"]


def _rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _healthy(timeout_s: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{FLM_BASE}/v1/models",
                                    timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


class _FlmServe:
    """One flm serve child for one candidate; always reaped."""

    def __init__(self, model: str):
        self.model = model
        self.proc: subprocess.Popen | None = None

    def __enter__(self):
        self.proc = subprocess.Popen(
            ["flm", "serve", self.model, "--host", "127.0.0.1",
             "-p", str(FLM_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 180.0
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"flm serve exited rc={self.proc.returncode} "
                    f"for {self.model}")
            if _healthy():
                return self
            time.sleep(0.5)
        raise RuntimeError(f"flm serve not healthy in 180s: "
                           f"{self.model}")

    def __exit__(self, *exc):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        # The port must be free before the next candidate starts.
        deadline = time.time() + 20.0
        while time.time() < deadline and _healthy(timeout_s=1.0):
            time.sleep(0.5)
        return None


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
    report = {"slice": "HG-NPU", "case_set": "benchmarks/hg_t2_cases.py",
              "n_cases": len(CASES), "spec": SPEC,
              "candidates": candidates,
              "method": "identical prompts via SelectiveModelBackend; "
                        "cold first call measured separately; warm "
                        "latency = median over 3 hard-case passes; "
                        "accuracy graded on pass 1 only"}
    if INCUMBENT_REPORT.exists():
        inc = json.loads(INCUMBENT_REPORT.read_text())
        pick = inc.get("pick")
        if pick and pick in inc.get("models", {}):
            e = inc["models"][pick]
            report["incumbent_gpu_pick"] = {
                "model": pick,
                "accuracy": e.get("accuracy"),
                "accuracy_hard": e.get("accuracy_hard"),
                "model_median_latency_ms":
                    e.get("model_median_latency_ms"),
                "warmup_ms": e.get("warmup_ms")}
    rules_rows, rules_lat = _run(KeywordBackend(), CASES)
    report["rules_only"] = _summarize(rules_rows, rules_lat)
    print(f"rules-only: acc={report['rules_only']['accuracy']} "
          f"hard={report['rules_only']['accuracy_hard']}")
    hard_cases = [c for c in CASES if c["kind"] == "hard"]
    report["models"] = {}
    for model in candidates:
        entry: dict = {}
        try:
            with _FlmServe(model) as serve:
                assert serve.proc is not None
                entry["flm_pid"] = serve.proc.pid
                entry["idle_rss_kib"] = _rss_kib(serve.proc.pid)
                engine = FlmEngine(model=model, base_url=FLM_BASE)
                health = engine.health()
                entry["health"] = health
                if health.get("status") != "ok" or \
                        not health.get("model_present"):
                    entry["status"] = "unavailable"
                    report["models"][model] = entry
                    print(f"{model}: unavailable {health}")
                    continue
                backend = SelectiveModelBackend(
                    model_backend=build_flm_backend(
                        model=model, base_url=FLM_BASE))
                # Cold first call (serve just started; excluded from
                # warm numbers, recorded on its own).
                t0 = time.perf_counter()
                backend.evaluate({"text": "warmup ping"},
                                 DecisionSpec.from_dict(dict(SPEC)))
                entry["cold_first_call_ms"] = round(
                    (time.perf_counter() - t0) * 1000.0, 1)
                rows, lat = _run(backend, CASES)
                entry.update(_summarize(rows, lat))
                # Warm latency: two further hard-case passes.
                warm_lat = [r["latency_ms"] for r in rows
                            if r["model_used"]]
                for _ in range(2):
                    more, _lat = _run(backend, hard_cases)
                    warm_lat += [r["latency_ms"] for r in more
                                 if r["model_used"]]
                entry["model_median_latency_ms"] = round(
                    statistics.median(warm_lat), 1) if warm_lat else None
                entry["model_p95_latency_ms"] = round(
                    sorted(warm_lat)[int(0.95 * (len(warm_lat) - 1))],
                    1) if warm_lat else None
                entry["loaded_rss_kib"] = _rss_kib(serve.proc.pid)
                entry["status"] = "ok"
                print(f"{model}: acc={entry['accuracy']} "
                      f"hard={entry['accuracy_hard']} "
                      f"invoked={entry['model_invocations']} "
                      f"warm_median={entry['model_median_latency_ms']}ms "
                      f"cold={entry['cold_first_call_ms']}ms "
                      f"rss={entry['loaded_rss_kib']}KiB")
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
            "then lowest warm median model latency (HG-T2 rule)")
        inc = report.get("incumbent_gpu_pick") or {}
        best_acc = ok[pick]["accuracy"]
        report["matches_incumbent_accuracy"] = bool(
            inc and best_acc >= inc.get("accuracy", 2.0))
    else:
        report["pick"] = None
        report["pick_reason"] = "no candidate model was available"
        report["matches_incumbent_accuracy"] = False
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"pick: {report['pick']} — report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
