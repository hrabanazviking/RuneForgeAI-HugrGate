"""Interactive inspector REPL. Slice 436.
``hugrgate inspect`` drops the operator into a small read-eval loop
against a live service (or the in-process gate):

    hugrgate> backends
    hugrgate> decide spec.yaml state.json --backend keyword
    hugrgate> last
    hugrgate> quit

Every command prints human-readable output; errors are reported
inline and never kill the loop. ``Ctrl-D`` / ``quit`` exits cleanly.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from typing import Any, ClassVar

__all__ = ["InspectSession", "run_inspect"]

HELP = """\
commands:
  help                          show this help
  url [URL]                     show or switch the service URL
  health                        liveness probe
  protocol                      protocol advertisement
  backends                      list registered backends
  models                        list known models
  decide <spec> <state> [--backend NAME] [--policy FILE]
                                make one decision
  last                          show the last decision in detail
  quit | exit | q                leave the inspector
"""


class InspectSession:
    """One REPL session against a service URL (or in-process gate)."""

    def __init__(self, url: str | None = None) -> None:
        from hugrgate.client import HugrGateClient
        self.url = url or "http://127.0.0.1:8377"
        self.client = HugrGateClient(url=self.url)
        self.last_result: dict[str, Any] | None = None
        self.running = True

    # -- plumbing -----------------------------------------------------------
    def out(self, text: str) -> None:
        print(text)

    def close(self) -> None:
        self.client.close()

    # -- commands ------------------------------------------------------------
    def do_help(self, argv: list[str]) -> None:
        self.out(HELP.rstrip("\n"))

    def do_url(self, argv: list[str]) -> None:
        if not argv:
            self.out(self.url)
            return
        from hugrgate.client import HugrGateClient
        self.client.close()
        self.url = argv[0]
        self.client = HugrGateClient(url=self.url)
        self.out(f"now talking to {self.url}")

    def do_health(self, argv: list[str]) -> None:
        health = self.client.health()
        if health.get("reachable"):
            self.out(f"ok — version {health.get('version', '?')} "
                     f"uptime {health.get('uptime_s', '?')}s "
                     f"decisions {health.get('decisions_served', '?')}")
        else:
            self.out(f"UNREACHABLE — {health.get('error', '?')}")

    def do_protocol(self, argv: list[str]) -> None:
        try:
            proto = self.client.protocol()
        except Exception as e:  # noqa: BLE001 - REPL must not crash
            self.out(f"error: {e}")
            return
        self.out(f"protocol {proto.get('protocol_version')} "
                 f"(service {proto.get('service_version', '?')}) "
                 f"mode={proto.get('mode', 'http')}")

    def do_backends(self, argv: list[str]) -> None:
        try:
            infos = self.client.backends()
        except Exception as e:  # noqa: BLE001 - REPL must not crash
            self.out(f"error: {e}")
            return
        if not infos:
            self.out("(no backends)")
            return
        for info in infos:
            self.out(f"- {info.get('name')} "
                     f"(remote={info.get('is_remote')})")

    def do_models(self, argv: list[str]) -> None:
        from hugrgate.pool import shared_http_client_pool
        try:
            with shared_http_client_pool().acquire() as handle:
                response = handle.resource.get(
                    f"{self.url.rstrip('/')}/models", timeout=10.0)
            response.raise_for_status()
            body = response.json()
        except Exception as e:  # noqa: BLE001 - REPL must not crash
            self.out(f"error: {e}")
            return
        models = body if isinstance(body, list) else body.get("models", [])
        if not models:
            self.out("(no models)")
            return
        for m in models:
            self.out(f"- {m.get('name')} [{m.get('backend')}]")

    def do_decide(self, argv: list[str]) -> None:
        from hugrgate.errors import Abstention
        from hugrgate.loaders import load_policy, load_spec, load_state
        spec_file = state_file = policy_file = None
        backend_name = None
        rest = list(argv)
        positional: list[str] = []
        while rest:
            tok = rest.pop(0)
            if tok == "--backend" and rest:
                backend_name = rest.pop(0)
            elif tok == "--policy" and rest:
                policy_file = rest.pop(0)
            elif tok.startswith("--"):
                self.out(f"unknown flag: {tok}")
                return
            else:
                positional.append(tok)
        if len(positional) != 2:
            self.out("usage: decide <spec> <state> [--backend NAME] "
                     "[--policy FILE]")
            return
        spec_file, state_file = positional
        try:
            spec = load_spec(spec_file)
            state = load_state(state_file)
            policy = load_policy(policy_file) if policy_file else None
        except (ValueError, FileNotFoundError, KeyError) as e:
            self.out(f"error: {e}")
            return
        try:
            result = self.client.decide(state, spec, policy,
                                        backend_name=backend_name)
        except Abstention as e:
            self.out(f"abstained ({e.reason}): {e.message}")
            return
        except Exception as e:  # noqa: BLE001 - REPL must not crash
            self.out(f"error: {e}")
            return
        d = result.to_dict()
        self.last_result = d
        self.out(f"value={d['value']!r} p={d['probability']:.4f} "
                 f"backend={d['backend']} "
                 f"latency={d['latency_ms']:.1f}ms")

    def do_last(self, argv: list[str]) -> None:
        if self.last_result is None:
            self.out("no decision yet — run `decide` first")
            return
        import json
        d = self.last_result
        self.out(f"value: {d['value']!r}")
        self.out(f"probability: {d['probability']:.4f}")
        self.out(f"distribution: "
                 f"{json.dumps(d['distribution'], default=str)}")
        self.out(f"backend: {d['backend']} model: {d['model']}")
        self.out(f"metadata: {json.dumps(d['metadata'], default=str)}")

    def do_quit(self, argv: list[str]) -> None:
        self.running = False

    # -- loop ------------------------------------------------------------------
    _COMMANDS: ClassVar[dict[str, Callable[[InspectSession, list[str]],
                                             None]]] = {
        "help": do_help,
        "url": do_url,
        "health": do_health,
        "protocol": do_protocol,
        "backends": do_backends,
        "models": do_models,
        "decide": do_decide,
        "last": do_last,
        "quit": do_quit,
        "exit": do_quit,
        "q": do_quit,
    }

    def handle_line(self, line: str) -> None:
        try:
            argv = shlex.split(line)
        except ValueError as e:
            self.out(f"error: {e}")
            return
        if not argv:
            return
        cmd, rest = argv[0], argv[1:]
        func = self._COMMANDS.get(cmd)
        if func is None:
            self.out(f"unknown command: {cmd} (try `help`)")
            return
        func(self, rest)

    def run(self) -> int:
        try:
            import readline  # noqa: F401 - history support when present
        except ImportError:
            pass
        self.out(f"hugrgate inspector — talking to {self.url} "
                 "(type `help`, Ctrl-D to quit)")
        while self.running:
            try:
                line = input("hugrgate> ")
            except EOFError:
                break
            except KeyboardInterrupt:
                self.out("")
                break
            self.handle_line(line)
        self.out("bye.")
        return 0


def run_inspect(url: str | None = None) -> int:
    """Entry point for ``hugrgate inspect``."""
    session = InspectSession(url=url)
    try:
        return session.run()
    finally:
        session.close()
