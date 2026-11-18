"""HugrGate decision server — Tviheimr readiness slice HG-T1.

A long-running, localhost, plain-process server shape for HugrGate:

- ``POST /judge``  — request/response judgment: ``{state, spec, policy?}``
  in, decision-result JSON out. This is the Tviheimr-facing name for the
  same judgment the in-process runtime makes; ``POST /decide`` is kept
  as an alias so existing clients keep working.
- ``POST /events`` — event-intake endpoint: ``{events: [{...}, ...]}``
  (or a bare list). Each event is judged against a caller-supplied
  ``spec`` (per-batch or per-event) or a default categorical triage
  spec, and the per-event verdicts are returned in order. Nothing is
  dropped silently: a malformed event yields a per-event error entry,
  never a vanished event.
- ``GET /health`` — liveness/readiness probe with counters.
- ``GET /backends`` — registered backend names + capabilities.

Structured logging: every request emits one JSON log record (via
:mod:`hugrgate.log`'s ``JsonFormatter`` conventions) carrying
request_id, method, path, status, and latency_ms — metadata only,
never payload, per the package privacy rule.

Stdlib only (``http.server``): the decision-server form must run
anywhere HugrGate runs, including hosts where the optional FastAPI
``server`` extra is not installed. It delegates judgment to the
in-process :class:`~hugrgate.core.HugrGate` runtime with two honest
deterministic built-in backends (uniform + keyword overlap, mirroring
:mod:`hugrgate.server`'s baselines).

Runs as a plain process under its operator's control. Any resident /
boot-enabled service form is the owner's separate explicit decision —
never assumed here. Startup and shutdown are clean and boring:
``serve()`` handles SIGINT/SIGTERM, ``stop()`` drains and closes.
"""

from __future__ import annotations

import json
import math
import re
import signal
import threading
import time
import uuid
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hugrgate.backend import Backend
from hugrgate.core import HugrGate
from hugrgate.errors import HugrGateError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import policy_from_dict
from hugrgate.spec import DecisionSpec
from hugrgate.reflex_api import ReflexRegistry
from hugrgate.triage_profile import TriageProfile

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DecisionServer",
    "KeywordBackend",
    "UniformBackend",
    "build_gate",
    "main",
]

logger = get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8387

_WORD_RE = re.compile(r"[a-z0-9]+")
_MAX_BODY = 1_048_576


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    maximum = max(scores.values())
    exps = {k: math.exp(v - maximum) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


class UniformBackend(Backend):
    """Uniform-distribution baseline (mirrors hugrgate.server)."""

    name = "uniform"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical", "binary", "ordinal",
                               "numeric", "multilabel"],
                "deterministic": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal",
                             "numeric", "multilabel")

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        if spec.type == "numeric":
            assert spec.minimum is not None and spec.maximum is not None
            mid = (spec.minimum + spec.maximum) / 2.0
            return DecisionResult(value=mid, probability=0.5,
                                  distribution={}, uncertainty=1.0,
                                  backend=self.name, model="uniform-1.0")
        space = spec.value_space()
        dist = {v: 1.0 / len(space) for v in space}
        value: Any = [] if spec.type == "multilabel" else space[0]
        return DecisionResult(
            value=value,
            probability=dist[value] if value in dist else 0.0,
            distribution=dist, uncertainty=1.0, backend=self.name,
            model="uniform-1.0", metadata={"baseline": True})


class KeywordBackend(Backend):
    """Deterministic keyword-overlap classifier (mirrors server)."""

    name = "keyword"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical", "binary", "ordinal"],
                "deterministic": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal")

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        text = " ".join(str(v) for v in state.values()
                        if isinstance(v, (str, int, float, bool)))
        state_toks = set(_tokens(text))
        if spec.type == "binary":
            label_kws = {"true": set(_tokens(spec.statement or "")),
                         "false": set()}
        else:
            label_kws = {label: set(_tokens(label))
                         for label in spec.value_space()}
        scores = {}
        for label, kws in label_kws.items():
            score = 0
            for tok in state_toks:
                for kw in kws:
                    if tok == kw or (len(tok) >= 4 and len(kw) >= 4
                                     and (tok.startswith(kw)
                                          or kw.startswith(tok))):
                        score += 1
                        break
            scores[label] = float(score)
        if sum(scores.values()) <= 0.0:
            dist = {label: 1.0 / len(scores) for label in scores}
        else:
            dist = _softmax(scores)
        value = max(dist, key=lambda k: dist[k])
        return DecisionResult(value=value, probability=dist[value],
                              distribution=dist, backend=self.name,
                              model="keyword-1.0",
                              metadata={"scores": scores})


def build_gate() -> HugrGate:
    """A HugrGate runtime with the deterministic built-in backends."""
    gate = HugrGate()
    gate.register(UniformBackend())
    gate.register(KeywordBackend())
    return gate


_DEFAULT_EVENT_SPEC = {
    "type": "categorical",
    "options": ["routine", "attention", "escalate"],
}


class DecisionServer:
    """Threaded localhost decision server (plain process, HG-T1)."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 gate: HugrGate | None = None) -> None:
        self.host = host
        self.port = port
        self.gate = gate or build_gate()
        self._started_at: float | None = None
        self._judgments = 0
        self._events = 0
        self._errors = 0
        self._reflex_registry = ReflexRegistry()
        self._reflex_judgments = 0
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------
    @property
    def address(self) -> tuple[str, int]:
        if self._httpd is not None:
            return self._httpd.server_address[:2]
        return (self.host, self.port)

    def start(self) -> None:
        """Bind and serve in a background thread. Clean, boring."""
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="hugrgate-decision",
            daemon=True)
        self._thread.start()
        logger.info("decision server listening on %s:%s",
                    *self.address)

    def stop(self) -> None:
        """Stop accepting, close the socket, join the thread."""
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._httpd = None
        self._thread = None
        logger.info("decision server stopped")

    def __enter__(self) -> DecisionServer:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()
        return None

    def serve(self) -> None:
        """Serve in the foreground until SIGINT/SIGTERM (plain process)."""
        self.start()
        assert self._httpd is not None
        stopped = threading.Event()

        def _signal(_signum: int, _frame: Any) -> None:
            stopped.set()

        old_int = signal.signal(signal.SIGINT, _signal)
        old_term = signal.signal(signal.SIGTERM, _signal)
        try:
            stopped.wait()
        finally:
            signal.signal(signal.SIGINT, old_int)
            signal.signal(signal.SIGTERM, old_term)
            self.stop()

    # -- request logic (transport-independent) -------------------------
    def health(self) -> dict[str, Any]:
        with self._lock:
            judgments, events, errors = (self._judgments, self._events,
                                         self._errors)
        return {
            "status": "ok",
            "service": "hugrgate-decision-server",
            "slice": "HG-T1",
            "uptime_s": (round(time.time() - self._started_at, 3)
                         if self._started_at else 0.0),
            "judgments": judgments,
            "events": events,
            "errors": errors,
            "backends": sorted(self.gate.registry.list()),
        }

    def judge(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """One judgment: {state, spec, policy?, backend?} -> result."""
        state = body.get("state")
        spec_dict = body.get("spec")
        if not isinstance(state, Mapping):
            raise _BadRequest("judge needs a 'state' object")
        if not isinstance(spec_dict, Mapping):
            raise _BadRequest("judge needs a 'spec' object")
        spec = DecisionSpec.from_dict(dict(spec_dict))
        policy = (policy_from_dict(body["policy"])
                  if isinstance(body.get("policy"), Mapping)
                  else DecisionPolicy(minimum_probability=0.0))
        result = self.gate.decide(dict(state), spec, policy,
                                  backend_name=body.get("backend"))
        with self._lock:
            self._judgments += 1
        return result.to_dict()

    def triage(self, body: Any) -> dict[str, Any]:
        """HG-T3 triage: {events:[...]} -> per-event verdicts, none dropped."""
        if isinstance(body, list): events=body
        elif isinstance(body, Mapping): events=body.get('events')
        else: raise _BadRequest('triage body must be an object or a list')
        if not isinstance(events, list) or not events: raise _BadRequest("'events' must be a non-empty list")
        verdicts=TriageProfile().triage_stream(events)
        with self._lock: self._events += len(events)
        return {'accepted': len(events), 'verdicts': verdicts, 'shed': sum(1 for v in verdicts if v['route']=='shed')}

    def register_reflex(self, body: Any) -> dict[str, Any]:
        """HG-T4: declare a reflex {name, action, pattern, consumer?}."""
        if not isinstance(body, Mapping):
            raise _BadRequest('reflex body must be an object')
        try:
            entry = self._reflex_registry.register(body.get('name'), body.get('action'), body.get('pattern'), consumer=body.get('consumer'))
        except ValueError as e:
            raise _BadRequest(str(e)) from e
        return {'registered': entry, 'reflexes': len(self._reflex_registry)}

    def list_reflexes(self) -> dict[str, Any]:
        return {'consumer': self._reflex_registry.consumer, 'reflexes': self._reflex_registry.list_reflexes()}

    def judge_reflexes(self, body: Any) -> dict[str, Any]:
        """HG-T4: judge one event or {events:[...]} against declared reflexes."""
        if isinstance(body, Mapping) and isinstance(body.get('events'), list):
            out = self._reflex_registry.judge_stream(body['events'])
            with self._lock:
                self._reflex_judgments += out['events']
            return out
        if isinstance(body, Mapping) and body.get('kind'):
            res = self._reflex_registry.judge_one(body)
            with self._lock:
                self._reflex_judgments += 1
            return res
        raise _BadRequest("reflex judge needs an event or {'events': [...]}")

    def intake_events(self, body: Any) -> dict[str, Any]:
        """Event batch intake. Per-event verdicts, nothing dropped."""
        if isinstance(body, list):
            events, batch_spec = body, None
        elif isinstance(body, Mapping):
            events = body.get("events")
            batch_spec = body.get("spec")
        else:
            raise _BadRequest("events body must be an object or a list")
        if not isinstance(events, list) or not events:
            raise _BadRequest("'events' must be a non-empty list")
        verdicts: list[dict[str, Any]] = []
        for idx, event in enumerate(events):
            if not isinstance(event, Mapping):
                verdicts.append({"index": idx, "ok": False,
                                 "error": "event is not an object"})
                continue
            spec_dict = event.get("spec") or batch_spec \
                or _DEFAULT_EVENT_SPEC
            state = event.get("state") or {
                k: v for k, v in event.items() if k != "spec"}
            try:
                result = self.judge({"state": dict(state),
                                     "spec": dict(spec_dict)})
                verdicts.append({"index": idx, "ok": True,
                                 "result": result})
            except Exception as e:  # noqa: BLE001 - per-event, reported
                verdicts.append({"index": idx, "ok": False,
                                 "error": f"{type(e).__name__}: {e}"})
        with self._lock:
            self._events += len(events)
        return {"accepted": len(events), "verdicts": verdicts}


class _BadRequest(ValueError):
    pass


def _make_handler(server: DecisionServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass  # structured logging below replaces the default log

        def _send(self, status: int, payload: dict[str, Any],
                  request_id: str, started: float) -> None:
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Request-ID", request_id)
            self.end_headers()
            self.wfile.write(raw)
            latency = round((time.perf_counter() - started) * 1000, 3)
            logger.info(json.dumps({
                "request_id": request_id, "method": self.command,
                "path": self.path, "status": status,
                "latency_ms": latency}))

        def _body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                raise _BadRequest("request body too large")
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw.decode() or "null")
            except (ValueError, UnicodeDecodeError) as e:
                raise _BadRequest(f"invalid JSON body: {e}") from e

        def _dispatch(self, fn) -> None:
            request_id = self.headers.get("X-Request-ID") \
                or uuid.uuid4().hex
            started = time.perf_counter()
            try:
                status, payload = fn()
            except _BadRequest as e:
                status, payload = 400, {"error": str(e)}
            except HugrGateError as e:
                status, payload = 422, {"error": f"{type(e).__name__}: {e}"}
            except Exception as e:  # noqa: BLE001 - fail as JSON, not hang
                status, payload = 500, {"error": f"{type(e).__name__}: {e}"}
            if status >= 400:
                with server._lock:
                    server._errors += 1
            self._send(status, payload, request_id, started)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path == "/health":
                self._dispatch(lambda: (200, server.health()))
            elif self.path == "/reflexes":
                self._dispatch(lambda: (200, server.list_reflexes()))
            elif self.path == "/backends":
                def _backends():
                    infos = {}
                    for name in server.gate.registry.list():
                        backend = server.gate.registry.get(name)
                        if backend is not None:
                            infos[name] = backend.capabilities()
                    return 200, {"backends": infos}
                self._dispatch(_backends)
            else:
                self._dispatch(lambda: (404, {"error": "not found"}))

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if self.path in ("/judge", "/decide"):
                self._dispatch(lambda: (200, server.judge(self._body())))
            elif self.path == "/triage":
                self._dispatch(lambda: (200, server.triage(self._body())))
            elif self.path == "/reflexes":
                self._dispatch(lambda: (201, server.register_reflex(self._body())))
            elif self.path == "/reflex/judge":
                self._dispatch(lambda: (200, server.judge_reflexes(self._body())))
            elif self.path == "/events":
                self._dispatch(
                    lambda: (200, server.intake_events(self._body())))
            else:
                self._dispatch(lambda: (404, {"error": "not found"}))

    return Handler


def main(argv: list[str] | None = None) -> int:
    """Plain-process entry point: hugrgate decision server (HG-T1)."""
    import argparse

    from hugrgate.log import configure_logging

    parser = argparse.ArgumentParser(prog="hugrgate-decision-server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    configure_logging("INFO", json_format=True)
    DecisionServer(host=args.host, port=args.port).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
