"""Flamegraphs from decision profiles. Slice 277.

Builds on :mod:`hugrgate.profiling` (slice 276): a
:class:`ProfileReport` carries the full cProfile call graph, and this
module turns it into

- **folded stacks** — the ``a;b;c <weight>`` text format understood by
  flamegraph tooling, derived deterministically from the profile's
  caller→callee edges (weights are cumulative milliseconds, not
  samples — this is a *profile* flamegraph, honest about its source);
- **self-contained SVG** — :class:`FlameGraph` renders proportional
  frames with tooltips and labels, no JavaScript, no external assets;
- **baseline artifacts** — :func:`write_baseline` persists folded
  stacks + SVG + JSON metadata (host, timestamp, HugrGate version) so
  later runs can be diffed against a known shape.

Privacy: frame names come from the profile; callers must apply the same
strict-privacy suppression as :mod:`hugrgate.profiling` before persisting
a baseline that names backend internals.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.errors import ProfilingError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "FlameGraph",
    "FoldedStacks",
    "StackFrame",
    "baseline_metadata",
    "write_baseline",
]

#: Schema version for baseline artifact metadata.
ARTIFACT_SCHEMA = 1


@dataclass
class StackFrame:
    """One folded stack: semicolon-joined frames + cumulative weight (ms)."""
    stack: str
    weight_ms: float
    depth: int


@dataclass
class FoldedStacks:
    """Folded-stack view of a profile's call graph."""
    frames: list[StackFrame] = field(default_factory=list)
    total_weight_ms: float = 0.0
    label: str = ""

    @classmethod
    def from_pstats(cls, stats: Any, label: str = "") -> FoldedStacks:
        """Build folded stacks directly from :class:`pstats.Stats`.

        Uses the real caller map (``stats.stats[func][4]``), so the
        tree is exact, not approximated.
        """
        raw = stats.stats
        if not raw:
            raise ProfilingError("cannot build flamegraph from empty stats")

        def _name(func: tuple[str, int, str]) -> str:
            filename, _lineno, funcname = func
            module = filename.rsplit("/", 1)[-1]
            if module.endswith(".py"):
                module = module[:-3]
            return f"{module}:{funcname}"

        names = {func: _name(func) for func in raw}
        # children: func -> list of (child_func, child_cumtime)
        children: dict[Any, list[tuple[Any, float]]] = {f: [] for f in raw}
        has_caller: set[Any] = set()
        for func, (_cc, _nc, _tt, _ct, callers) in raw.items():
            # Caller entries are 4-tuples (cc, nc, tt, ct) — no sub-map.
            for caller, (_ccc, _ncc, _tcc, cct) in callers.items():
                if caller in children:
                    children[caller].append((func, cct))
                    has_caller.add(func)
        roots = [f for f in raw if f not in has_caller]
        if not roots:  # degenerate (all recursive): pick the heaviest
            roots = [max(raw, key=lambda f: raw[f][3])]

        frames: list[StackFrame] = []
        total = 0.0

        def _walk(func: Any, stack: tuple[str, ...], seen: set[Any]) -> None:
            nonlocal total
            name = names[func]
            path = (*stack, name)
            kids = [(c, w) for c, w in children[func] if c not in seen]
            if not kids:
                _cc, _nc, _tt, ct, _callers = raw[func]
                weight = ct * 1000.0
                frames.append(StackFrame(";".join(path), weight,
                                         len(path)))
                total += weight
                return
            for child, _w in sorted(kids, key=lambda kv: names[kv[0]]):
                _walk(child, path, seen | {func})

        for root in sorted(roots, key=lambda f: names[f]):
            _walk(root, (), set())
        return cls(frames=frames, total_weight_ms=total, label=label)

    def to_folded(self) -> str:
        """Render the ``stack weight`` text format (descending weight)."""
        lines = [
            f"{f.stack} {f.weight_ms:.3f}"
            for f in sorted(self.frames, key=lambda f: f.weight_ms,
                            reverse=True)
        ]
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_weight_ms": self.total_weight_ms,
            "frame_count": len(self.frames),
            "frames": [
                {"stack": f.stack, "weight_ms": f.weight_ms,
                 "depth": f.depth}
                for f in self.frames
            ],
        }


def _frame_color(name: str) -> str:
    digest = hashlib.md5(name.encode("utf-8")).digest()
    # Warm palette keyed off the hash, kept readable on dark backgrounds.
    r = 200 + digest[0] % 55
    g = 90 + digest[1] % 90
    b = 40 + digest[2] % 60
    return f"rgb({r},{g},{b})"


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class FlameGraph:
    """Render folded stacks as a self-contained SVG flamegraph."""

    def __init__(self, width: int = 1200, frame_height: int = 22,
                 font_size: int = 12) -> None:
        if width < 200:
            raise ProfilingError(f"flamegraph width must be >= 200, "
                                 f"got {width}")
        if frame_height < 8:
            raise ProfilingError("frame_height must be >= 8, "
                                 f"got {frame_height}")
        self.width = width
        self.frame_height = frame_height
        self.font_size = font_size

    def render_svg(self, stacks: FoldedStacks, title: str = "") -> str:
        """Render ``stacks`` to an SVG document string."""
        if not stacks.frames:
            raise ProfilingError("cannot render an empty folded-stack set")
        total = stacks.total_weight_ms
        if total <= 0:
            raise ProfilingError("flamegraph total weight must be > 0")
        max_depth = max(f.depth for f in stacks.frames)
        height = max_depth * self.frame_height + 60

        # Lay out frames: sort by stack so siblings are adjacent, then
        # place each leaf's weight left-to-right at its depth.  Parent
        # frames are the union of their children's spans.
        spans: dict[tuple[str, ...], list[float]] = {}
        ordered = sorted(stacks.frames, key=lambda f: f.stack)
        x = 0.0
        for frame in ordered:
            w = frame.weight_ms / total * self.width
            parts = tuple(frame.stack.split(";"))
            for depth in range(1, len(parts) + 1):
                key = parts[:depth]
                span = spans.setdefault(key, [x, x])
                span[1] = x + w
            x += w

        rects = []
        for key in sorted(spans, key=lambda k: (len(k), k)):
            depth = len(key)
            x0, x1 = spans[key]
            name = key[-1]
            color = _frame_color(";".join(key))
            y = height - 40 - depth * self.frame_height
            w = x1 - x0
            label = _escape(name) if w > 60 else ""
            rects.append(
                f'<g><title>{_escape(";".join(key))} '
                f'({(x1 - x0) / self.width * total:.2f} ms)</title>'
                f'<rect x="{x0:.2f}" y="{y}" width="{w:.2f}" '
                f'height="{self.frame_height - 1}" fill="{color}" '
                f'stroke="#1a1a1a" stroke-width="0.5"/>'
                + (f'<text x="{x0 + 4:.2f}" y="{y + self.font_size + 2}" '
                   f'font-size="{self.font_size}" fill="#f5f0e8" '
                   f'font-family="monospace">{label}</text>' if label else "")
                + "</g>")

        svg = [
            f'<svg width="{self.width}" height="{height}" '
            'xmlns="http://www.w3.org/2000/svg" role="img">',
            f'<rect width="{self.width}" height="{height}" fill="#14100c"/>',
            f'<text x="12" y="24" font-size="16" fill="#f5f0e8" '
            f'font-family="monospace">{_escape(title or stacks.label or "flamegraph")}</text>',
            f'<text x="12" y="44" font-size="12" fill="#a89c86" '
            f'font-family="monospace">total {total:.2f} ms · '
            f'{len(stacks.frames)} stacks · profile flamegraph '
            f'(cumulative ms, not samples)</text>',
            *rects,
            "</svg>",
        ]
        return "\n".join(svg)


def baseline_metadata(label: str) -> dict[str, Any]:
    """Metadata stamped onto every baseline artifact."""
    return {
        "schema": ARTIFACT_SCHEMA,
        "label": label,
        "hugrgate_version": HUGRGATE_VERSION,
        "created_unix": time.time(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        },
        "note": "cumulative-ms profile flamegraph, not sampled; "
                "compare shapes, not absolute timings, across hosts",
    }


def write_baseline(stacks: FoldedStacks, svg: str,
                   directory: str | Path, label: str) -> dict[str, Path]:
    """Persist a flamegraph baseline: folded stacks + SVG + metadata JSON.

    Returns the written paths.  Raises :class:`ProfilingError` when the
    stacks are empty.
    """
    if not stacks.frames:
        raise ProfilingError("refusing to write an empty flamegraph baseline")
    outdir = Path(directory)
    outdir.mkdir(parents=True, exist_ok=True)
    folded_path = outdir / f"{label}.folded"
    svg_path = outdir / f"{label}.svg"
    meta_path = outdir / f"{label}.json"
    folded_path.write_text(stacks.to_folded(), encoding="utf-8")
    svg_path.write_text(svg, encoding="utf-8")
    meta_path.write_text(json.dumps(baseline_metadata(label), indent=2),
                         encoding="utf-8")
    logger.info("wrote flamegraph baseline %s (%d stacks)", label,
                len(stacks.frames))
    return {"folded": folded_path, "svg": svg_path, "meta": meta_path}
