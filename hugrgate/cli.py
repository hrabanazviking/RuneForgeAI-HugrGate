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
from typing import Any

from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "build_parser",
    "cmd_backends",
    "cmd_bench",
    "cmd_completion",
    "cmd_decide",
    "cmd_doctor",
    "cmd_health",
    "cmd_inspect",
    "cmd_models",
    "cmd_openapi",
    "cmd_report",
    "cmd_serve",
    "load_policy",
    "load_spec",
    "load_state",
    "main",
]


def _load_doc(path: str) -> Any:
    """Load a JSON or YAML document (YAML is a superset of JSON)."""
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_spec(path: str) -> DecisionSpec:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"spec file {path} must contain a mapping")
    return DecisionSpec.from_dict(doc)


def load_state(path: str) -> dict[str, Any]:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"state file {path} must contain a mapping")
    return doc


def load_policy(path: str) -> DecisionPolicy:
    from hugrgate.serde import policy_from_dict
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"policy file {path} must contain a mapping")
    return policy_from_dict(doc)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


# --- output formatting (slice 435) -------------------------------------------


def _flatten(value: Any) -> str:
    """Render a value as a single table cell."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _render_table(rows: list[dict[str, Any]],
                  columns: list[str]) -> str:
    """Render rows as an aligned plain-text table (no dependencies)."""
    widths = [len(c) for c in columns]
    cells = [[_flatten(r.get(c, "")) for c in columns] for r in rows]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(c.ljust(widths[i])
                       for i, c in enumerate(columns))]
    lines.append("  ".join("-" * w for w in widths))
    for row in cells:
        lines.append("  ".join(cell.ljust(widths[i])
                               for i, cell in enumerate(row)))
    return "\n".join(lines)


def _emit(args: argparse.Namespace, payload: Any,
          table: tuple[list[dict[str, Any]], list[str]] | None = None
          ) -> None:
    """Print ``payload`` as JSON (default) or as a table.

    ``table`` is ``(rows, columns)`` used when ``--format table`` is
    given; commands without a tabular form fall back to JSON.
    """
    fmt = getattr(args, "format", "json")
    if fmt == "table" and table is not None:
        rows, columns = table
        print(_render_table(rows, columns))
    elif fmt == "yaml":
        import yaml
        print(yaml.safe_dump(json.loads(json.dumps(payload,
                                                   default=str)),
                             default_flow_style=False,
                             sort_keys=False).rstrip("\n"))
    else:
        _print_json(payload)


def cmd_decide(args: argparse.Namespace) -> int:
    from hugrgate.errors import Abstention
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
    _emit(args, {"abstained": False, "decision": result.to_dict()},
          ([{k: result.to_dict().get(k) for k in
             ("value", "probability", "backend", "model",
              "latency_ms")}],
           ["value", "probability", "backend", "model",
            "latency_ms"]))
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
    _emit(args, {"backends": infos},
          (infos, ["name", "is_remote", "estimated_latency_ms",
                   "estimated_cost"]))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if args.url:
        from hugrgate.pool import shared_http_client_pool
        # Slice 290: acquire from the process-wide pooled clients instead
        # of minting (and TLS-handshaking) a throwaway client per command.
        with shared_http_client_pool().acquire() as handle:
            response = handle.resource.get(
                f"{args.url.rstrip('/')}/models", timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get(
            "models", [])
        _emit(args, payload, (rows, ["name", "backend", "spec_types",
                                    "description"]))
    else:
        from dataclasses import asdict

        from hugrgate.server import list_models
        models = [asdict(m) for m in list_models()]
        _emit(args, {"models": models},
              (models, ["name", "backend", "spec_types", "description"]))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    from hugrgate.client import HugrGateClient
    client = HugrGateClient(url=args.url or "http://127.0.0.1:8377")
    try:
        health = client.health()
        _emit(args, health,
              ([health], ["status", "version", "reachable",
                          "uptime_s", "decisions_served"]))
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
    with open(args.dataset, encoding="utf-8") as f:
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
    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)
    text = render_markdown(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote markdown report: {args.out}")
    else:
        print(text)
    return 0


def cmd_openapi(args: argparse.Namespace) -> int:
    """Dump the stabilized OpenAPI schema (slice 427)."""
    from hugrgate.server import dump_openapi_schema
    schema = dump_openapi_schema()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        print(f"wrote OpenAPI schema: {args.out}")
    else:
        _print_json(schema)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check that a HugrGate service is reachable and coherent.

    Slice 435: runs the checks an operator needs before trusting a
    deployment — reachability, protocol version agreement, backend
    inventory, and a live end-to-end decision. Prints one line per
    check and exits non-zero when anything fails.
    """
    from hugrgate.client import HugrGateClient
    from hugrgate.protocol import PROTOCOL_VERSION
    from hugrgate.spec import DecisionSpec

    url = args.url or "http://127.0.0.1:8377"
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"[{'ok' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    client = HugrGateClient(url=url, fallback_inprocess=False)
    try:
        health = client.health()
        reachable = bool(health.get("reachable"))
        check("service reachable", reachable,
              url if not reachable else
              f"version {health.get('version', '?')}")
        if reachable:
            try:
                proto = client.protocol()
                agreed = (proto.get("protocol_version")
                          == PROTOCOL_VERSION)
                check("protocol version agreement", agreed,
                      f"service={proto.get('protocol_version')} "
                      f"client={PROTOCOL_VERSION}")
            except Exception as e:  # noqa: BLE001 - probe must not crash
                check("protocol version agreement", False, str(e))
            try:
                backends = client.backends()
                check("backend inventory", len(backends) > 0,
                      f"{len(backends)} backend(s): "
                      + ", ".join(b.get("name", "?")
                                   for b in backends))
            except Exception as e:  # noqa: BLE001 - probe must not crash
                check("backend inventory", False, str(e))
            try:
                spec = DecisionSpec.from_dict(
                    {"type": "categorical", "options": ["a", "b"]})
                result = client.decide({"doctor": 1.0}, spec)
                check("end-to-end decision", True,
                      f"value={result.value} "
                      f"backend={result.backend}")
            except Exception as e:  # noqa: BLE001 - probe must not crash
                check("end-to-end decision", False, str(e))
    finally:
        client.close()
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"\ndoctor: {len(failed)} check(s) failed: "
              + ", ".join(failed))
        return 1
    print("\ndoctor: all checks passed")
    return 0


_COMPLETION_SCRIPTS = {
    "bash": """\
# hugrgate bash completion (generated by `hugrgate completion bash`)
# Install: save as /etc/bash_completion.d/hugrgate or source from ~/.bashrc
_hugrgate_complete() {
    local cur prev cmds
    cmds="{commands}"
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
        return 0
    fi
    case "$prev" in
        --format) COMPREPLY=( $(compgen -W "json table yaml" -- "$cur") );;
        --backend) COMPREPLY=( $(hugrgate backends 2>/dev/null | grep -o '"name": "[^"]*"' | cut -d'"' -f4) );;
        --url) COMPREPLY=();;
        *) COMPREPLY=( $(compgen -f -- "$cur") );;
    esac
}
complete -F _hugrgate_complete hugrgate
""",
    "zsh": """\
# hugrgate zsh completion (generated by `hugrgate completion zsh`)
# Install: save as _hugrgate somewhere on your $fpath
#compdef hugrgate
_hugrgate() {
    local -a commands
    commands=({commands_quoted})
    _arguments -C \\
        '--format[output format]:format:(json table yaml)' \\
        '--url[service URL]:url:' \\
        '1: :->command' \\
        '*:: :->args'
    case $state in
        command) _describe 'command' commands ;;
    esac
}
_hugrgate
""",
    "fish": """\
# hugrgate fish completion (generated by `hugrgate completion fish`)
# Install: save as ~/.config/fish/completions/hugrgate.fish
for cmd in {commands}; complete -c hugrgate -n '__fish_use_subcommand' -f -a $cmd; end
complete -c hugrgate -n '__fish_seen_subcommand_from decide backends models health' -l format -f -a "json table yaml"
complete -c hugrgate -l url -f -r
""",
}


def cmd_completion(args: argparse.Namespace) -> int:
    """Print a shell completion script (slice 435)."""
    commands = _command_names(build_parser())
    # Plain .replace(), not .format(): the scripts contain shell
    # braces that must not be interpreted as format fields.
    script = _COMPLETION_SCRIPTS[args.shell]
    script = script.replace("{commands}",
                            " ".join(commands))
    script = script.replace("{commands_quoted}",
                            " ".join(f'"{c}"' for c in commands))
    print(script, end="")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Drop into the interactive inspector REPL (slice 436)."""
    from hugrgate.inspect import run_inspect
    return run_inspect(args.url)


def _command_names(parser: argparse.ArgumentParser) -> list[str]:
    """Sorted subcommand names (for completion and did-you-mean)."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    return []


def build_parser() -> argparse.ArgumentParser:
    import difflib
    from typing import NoReturn

    class _Parser(argparse.ArgumentParser):
        """argparse with did-you-mean for mistyped subcommands."""

        def error(self, message: str) -> NoReturn:
            import re
            m = re.search(r"invalid choice: '([^']+)'", message)
            if m:
                near = difflib.get_close_matches(
                    m.group(1), _command_names(self), n=1)
                if near:
                    message += f"\ndid you mean '{near[0]}'?"
            super().error(message)

    parser = _Parser(
        prog="hugrgate",
        description="HugrGate — local-first probabilistic decision runtime.")
    parser.add_argument("--format", default="json",
                        choices=["json", "table", "yaml"],
                        help="output format (default: json)")
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

    p = sub.add_parser("openapi", help="dump the stabilized OpenAPI schema")
    p.add_argument("--out", default=None,
                   help="write schema JSON to a file (default: stdout)")
    p.set_defaults(func=cmd_openapi)

    p = sub.add_parser("doctor",
                       help="check service reachability and coherence")
    p.add_argument("--url", default=None,
                   help="service URL (default: http://127.0.0.1:8377)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("completion",
                       help="print a shell completion script")
    p.add_argument("shell", choices=["bash", "zsh", "fish"])
    p.set_defaults(func=cmd_completion)

    p = sub.add_parser("inspect",
                       help="interactive inspector REPL")
    p.add_argument("--url", default=None,
                   help="service URL (default: http://127.0.0.1:8377)")
    p.set_defaults(func=cmd_inspect)

    return parser


def main(argv: list[str] | None = None) -> int:
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
