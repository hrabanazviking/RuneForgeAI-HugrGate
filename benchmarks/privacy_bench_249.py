"""Slice 249 measurement artifact: privacy pipeline benchmarks.

Measures real per-operation latencies of the Campaign X privacy
pipeline on this machine: secret scanning, PII scrubbing,
redaction, local-only enforcement, full payload compilation,
SealedBox seal/open, token vault round-trips, audit logging,
and dry-run evaluation. No numbers are invented: every figure
is measured on this run.

Usage: python benchmarks/privacy_bench_249.py [--rounds N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import secrets
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_audit import PrivacyAuditLog
from hugrgate.privacy_crypto import SealedBox
from hugrgate.privacy_dryrun import PrivacyDryRun
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_payload import RemotePayloadCompiler
from hugrgate.privacy_pii import PIIScrubber, RegexPIIDetector
from hugrgate.privacy_redact import MaskRedactor, RedactionPipeline
from hugrgate.privacy_secrets import SecretScanner
from hugrgate.privacy_tokens import TokenVault


class _Remote:
    name = "bench-cloud"
    is_remote = True


def _states(seed: int, n: int) -> list[dict]:
    rng = random.Random(seed)
    words = ["alpha", "beta", "note", "query", "user", "email"]
    states = []
    for _ in range(n):
        state = {rng.choice(words) + str(i): rng.choice(words)
                 for i in range(rng.randint(5, 40))}
        state["transcript"] = ("contact john.doe@example.com or "
                               "555-123-4567 about ssn 123-45-6789")
        states.append(state)
    return states


def _measure(fn, workloads: list, repeat: int = 1) -> dict:
    samples = []
    for item in workloads:
        start = time.perf_counter()
        for _ in range(repeat):
            fn(item)
        samples.append((time.perf_counter() - start) / repeat * 1000.0)
    samples.sort()
    n = len(samples)
    pct = lambda q: samples[min(n - 1, int(q * n))]  # noqa: E731
    return {"n": n, "mean_ms": statistics.fmean(samples),
            "min_ms": samples[0], "max_ms": samples[-1],
            "p50_ms": pct(0.50), "p95_ms": pct(0.95)}


def run_benchmark(seed: int = 249, rounds: int = 100) -> dict:
    """Run all privacy benchmarks; returns the artifact dict."""
    states = _states(seed, rounds)
    guard = PrivacyGuard()
    guard.payload_compiler = RemotePayloadCompiler(guard=guard)
    compiler = guard.payload_compiler
    policy = DecisionPolicy(privacy_class="standard",
                            remote_inference=True)
    labels = FieldLabels(local_only=["note0"])
    scanner = SecretScanner()
    scrubber = PIIScrubber(RegexPIIDetector())
    pipeline = RedactionPipeline(
        field_redactors={"query0": MaskRedactor()})
    vault = TokenVault(namespace="bench")
    key = secrets.token_bytes(32)
    audit = PrivacyAuditLog()
    dryrun = PrivacyDryRun(guard)
    backend = _Remote()
    secret_blob = SealedBox.seal(key, b"benchmark payload" * 64)

    results = []
    timed = [
        ("secret_scan", lambda s: scanner.scan_state(s)),
        ("pii_scrub", lambda s: scrubber.scrub_state(s)),
        ("redaction", lambda s: pipeline.apply_to_state(s)),
        ("local_only",
         lambda s: guard.enforce_local_only(s, labels, backend)),
        ("payload_compile",
         lambda s: compiler.compile(s, backend=backend, policy=policy)),
        ("seal", lambda s: SealedBox.seal(key, b"x" * 256)),
        ("unseal", lambda s: SealedBox.open(key, secret_blob)),
        ("tokenize", lambda s: vault.tokenize("bench-value")),
        ("audit_record",
         lambda s: audit.record("bench", fields=len(s))),
        ("dry_run",
         lambda s: dryrun.evaluate(s, backend=backend, policy=policy)),
    ]
    for name, fn in timed:
        cell = _measure(fn, states)
        cell["op"] = name
        results.append(cell)

    # Sanity: the timed paths are functionally correct.
    assert SealedBox.open(key, SealedBox.seal(key, b"ok")) == b"ok"
    assert audit.verify() is True

    return {
        "name": "privacy_bench_249",
        "seed": seed,
        "rounds": rounds,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                     time.localtime()),
        "unit": "milliseconds",
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=100)
    ap.add_argument("--seed", type=int, default=249)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "privacy_bench_249.json"))
    args = ap.parse_args()
    artifact = run_benchmark(seed=args.seed, rounds=args.rounds)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
    print(f"wrote {args.out}")
    for cell in artifact["results"]:
        print(f"  {cell['op']:15s} mean={cell['mean_ms']:8.3f}ms "
              f"p95={cell['p95_ms']:8.3f}ms (n={cell['n']})")


if __name__ == "__main__":
    main()
