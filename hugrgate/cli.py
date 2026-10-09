"""HugrGate command-line interface. Slice 44.

Commands:
    hugrgate decide --spec spec.yaml --state state.json [--policy policy.yaml]
             [--backend NAME] [--url URL]
    hugrgate backends [--url URL]
    hugrgate models [--url URL]
    hugrgate health [--url URL]
    hugrgate serve [--host H] [--port P] [--unix-socket PATH] ...
    hugrgate bench --dataset DATASET.json --backends a,b --out report.json
    hugrgate report --report report.json [--out report.md]

Entry point: ``hugrgate`` (see ``pyproject.toml``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from hugrgate import DecisionPolicy, DecisionSpec

__all__ = [
    "load_spec",
    "load_state",
    "load_policy",
    "cmd_decide",
    "cmd_backends",
    "cmd_models",
    "cmd_health",
    "cmd_serve",
    "cmd_bench",
    "cmd_report",
    "build_parser",
    "main",
]


def _load_doc(path: str) -> Any:
    """Load a JSON or YAML document (YAML is a superset of JSON)."""
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_spec(path: str) -> DecisionSpec:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"spec file {path} must contain a mapping")
    return DecisionSpec.from_dict(doc)


def load_state(path: str) -> Dict[str, Any]:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"state file {path} must contain a mapping")
    return doc


def load_policy(path: str) -> DecisionPolicy:
    from hugrgate.client import policy_from_dict
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"policy file {path} must contain a mapping")
    return policy_from_dict(doc)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def cmd_decide(args: argparse.Namespace) -> int:
    from hugrgate import Abstention
    spec = load_spec(args.spec)
    state = load_state(args.state)
    policy = load_policy(args.policy) if args.policy else None
    if args.url:
        from hugrgate.client import HugrGateClient
        client = HugrGateClient(url=args.url)
        try:
            result = client.decide(state, spec, policy,
                                   backend_name=args.backend)
        except Abstention as e:
            _print_json({"abstained": True, "reason": e.reason,
                         "message": e.message})
            return 0
        finally:
            client.close()
    else:
        from hugrgate.server import build_gate
        gate = build_gate()
        try:
            result = gate.decide(state, spec, policy,
                                 backend_name=args.backend)
        except Abstention as e:
            _print_json({"abstained": True, "reason": e.reason,
                         "message": e.message})
            return 0
    _print_json({"abstained": False, "decision": result.to_dict()})
    return 0


def cmd_backends(args: argparse.Namespace) -> int:
    if args.url:
        from hugrgate.client import HugrGateClient
        client = HugrGateClient(url=args.url)
        try:
            infos = client.backends()
        finally:
            client.close()
    else:
        from hugrgate.server import build_gate
        gate = build_gate()
        infos = []
        for n in gate.registry.list():
            backend = gate.registry.get(n)
            if backend is None:  # defensive: list/get disagree
                continue
            infos.append({
                "name": n,
                "capabilities": backend.capabilities(),
                "is_remote": backend.is_remote})
    _print_json({"backends": infos})
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if args.url:
        import httpx
        with httpx.Client(trust_env=False) as _http:
            response = _http.get(f"{args.url.rstrip('/')}/models", timeout=10.0)
        response.raise_for_status()
        _print_json(response.json())
    else:
        from hugrgate.server import list_models
        from dataclasses import asdict
        _print_json({"models": [asdict(m) for m in list_models()]})
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    from hugrgate.client import HugrGateClient
    client = HugrGateClient(url=args.url or "http://127.0.0.1:8377")
    try:
        _print_json(client.health())
        return 0
    finally:
        client.close()


def cmd_serve(args: argparse.Namespace) -> int:
    from hugrgate.daemon import main as daemon_main
    daemon_argv = ["--host", args.host, "--port", str(args.port),
                   "--batch-window-ms", str(args.batch_window_ms),
                   "--max-batch", str(args.max_batch),
                   "--max-queue", str(args.max_queue)]
    if args.unix_socket:
        daemon_argv += ["--unix-socket", args.unix_socket]
    if args.client_policies:
        daemon_argv += ["--client-policies", args.client_policies]
    return daemon_main(daemon_argv)


def cmd_bench(args: argparse.Namespace) -> int:
    from hugrgate.bench import run_benchmark
    from hugrgate.server import build_gate
    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    policy = load_policy(args.policy) if args.policy else None
    backends = args.backends.split(",") if args.backends else None
    gate = build_gate()
    report = run_benchmark(dataset, gate, backends=backends, policy=policy,
                           max_items=args.max_items)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"wrote benchmark report: {args.out}")
    for name, metrics in report["backends"].items():
        acc = metrics.get("accuracy")
        acc_s = f"{acc:.3f}" if acc is not None else "n/a"
        print(f"  {name:12s} accuracy={acc_s} "
              f"brier={metrics['brier_score']:.3f} "
              f"ece={metrics['ece']:.3f} "
              f"p50={metrics['latency_p50_ms']:.1f}ms")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from hugrgate.bench_report import render_markdown
    with open(args.report, "r", encoding="utf-8") as f:
        report = json.load(f)
    text = render_markdown(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote markdown report: {args.out}")
    else:
        print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hugrgate",
        description="HugrGate — local-first probabilistic decision runtime.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("decide", help="make one decision")
    p.add_argument("--spec", required=True, help="spec YAML/JSON file")
    p.add_argument("--state", required=True, help="state JSON/YAML file")
    p.add_argument("--policy", default=None, help="policy YAML/JSON file")
    p.add_argument("--backend", default=None, help="backend name")
    p.add_argument("--url", default=None,
                   help="service URL (default: in-process)")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("backends", help="list available backends")
    p.add_argument("--url", default=None)
    p.set_defaults(func=cmd_backends)

    p = sub.add_parser("models", help="list known models")
    p.add_argument("--url", default=None)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("health", help="check service health")
    p.add_argument("--url", default=None)
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("serve", help="run the service daemon")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8377)
    p.add_argument("--unix-socket", default=None)
    p.add_argument("--batch-window-ms", type=float, default=5.0)
    p.add_argument("--max-batch", type=int, default=32)
    p.add_argument("--max-queue", type=int, default=1024)
    p.add_argument("--client-policies", default=None)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("bench", help="run a benchmark")
    p.add_argument("--dataset", required=True)
    p.add_argument("--backends", default=None,
                   help="comma-separated backend names (default: all)")
    p.add_argument("--policy", default=None)
    p.add_argument("--max-items", type=int, default=None)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("report", help="render a benchmark report as markdown")
    p.add_argument("--report", required=True)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """``hugrgate`` entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"hugrgate: file not found: {e.filename}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as e:
        print(f"hugrgate: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI top-level guard
        print(f"hugrgate: unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
