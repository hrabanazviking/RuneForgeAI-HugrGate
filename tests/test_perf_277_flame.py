"""Slice 277 — baseline flamegraphs.

Covers: FoldedStacks.from_pstats on a real cProfile call tree (roots,
weights, recursion cut), folded text format, FlameGraph SVG rendering
(success/failure/boundary), write_baseline artifacts, and validation
errors.
"""

from __future__ import annotations

import cProfile
import json
import pstats

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.errors import ProfilingError
from hugrgate.flame import (
    FlameGraph,
    FoldedStacks,
    baseline_metadata,
    write_baseline,
)
from hugrgate.profiling import DecisionProfiler
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow


def _leaf(n: int) -> int:
    total = 0
    for i in range(n):
        total += i * i
    return total


def _branch(n: int) -> int:
    return _leaf(n) + _leaf(n // 2)


def _root(n: int) -> int:
    return _branch(n) + 1


def _recurse(n: int) -> int:
    if n <= 0:
        return 0
    return _recurse(n - 1) + 1


def _profile_of(fn, *args):
    profiler = cProfile.Profile()
    profiler.enable()
    fn(*args)
    profiler.disable()
    return pstats.Stats(profiler)


def test_folded_stacks_from_real_call_tree():
    stats = _profile_of(_root, 500)
    stacks = FoldedStacks.from_pstats(stats, label="tree")
    assert stacks.frames
    assert stacks.total_weight_ms > 0
    # the leaf frame must appear at the bottom of some stack
    assert any(f.stack.split(";")[-1].endswith(":_leaf")
               for f in stacks.frames)
    # the root frame tops at least one stack
    assert any(f.stack.split(";")[0].endswith(":_root")
               for f in stacks.frames)
    assert all(f.depth >= 1 and f.weight_ms > 0 for f in stacks.frames)


def test_folded_stacks_recursion_terminates():
    stats = _profile_of(_recurse, 50)
    stacks = FoldedStacks.from_pstats(stats)
    assert stacks.frames
    assert stacks.total_weight_ms > 0


def test_folded_stacks_empty_stats_rejected():
    stats = pstats.Stats()
    with pytest.raises(ProfilingError):
        FoldedStacks.from_pstats(stats)


def test_to_folded_format():
    stats = _profile_of(_root, 200)
    stacks = FoldedStacks.from_pstats(stats)
    text = stacks.to_folded()
    lines = text.strip().split("\n")
    assert len(lines) == len(stacks.frames)
    for line in lines:
        stack, weight = line.rsplit(" ", 1)
        assert ";" in stack or stack  # single-frame stacks allowed
        assert float(weight) > 0


def test_svg_render_contains_frames_and_tooltips():
    stats = _profile_of(_root, 200)
    stacks = FoldedStacks.from_pstats(stats)
    svg = FlameGraph().render_svg(stacks, title="test-flame")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "test-flame" in svg
    assert "_leaf" in svg
    assert "<title>" in svg  # tooltips present
    assert "cumulative ms, not samples" in svg  # honesty caption


def test_svg_render_rejects_empty_or_bad_config():
    with pytest.raises(ProfilingError):
        FlameGraph().render_svg(FoldedStacks())
    with pytest.raises(ProfilingError):
        FlameGraph(width=100)


def test_write_baseline_produces_three_artifacts(tmp_path):
    stats = _profile_of(_root, 200)
    stacks = FoldedStacks.from_pstats(stats, label="base")
    svg = FlameGraph().render_svg(stacks)
    paths = write_baseline(stacks, svg, tmp_path, "unit-base")
    assert paths["folded"].read_text().strip()
    assert paths["svg"].read_text().startswith("<svg")
    meta = json.loads(paths["meta"].read_text())
    assert meta["schema"] == 1
    assert meta["label"] == "unit-base"
    assert meta["hugrgate_version"]
    assert "note" in meta


def test_write_baseline_rejects_empty():
    with pytest.raises(ProfilingError):
        write_baseline(FoldedStacks(), "<svg/>", "/tmp", "empty")


def test_baseline_metadata_shape():
    meta = baseline_metadata("x")
    assert meta["host"]["python"]
    assert meta["created_unix"] > 0


class StubBackend(Backend):
    name = "stub-277"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0, "b": 0.0})


def test_decide_path_flamegraph_end_to_end(tmp_path):
    """The full pipeline: profile a real decide → stacks → SVG → baseline."""
    gate = HugrGate()
    gate.register(StubBackend())
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.0)
    profiler = DecisionProfiler()
    _, stats, _wall = profiler.profile_raw(
        gate.decide, {"x": 1}, spec, policy)
    stacks = FoldedStacks.from_pstats(stats, label="decide")
    svg = FlameGraph().render_svg(stacks, title="decide() baseline")
    paths = write_baseline(stacks, svg, tmp_path, "decide")
    assert paths["folded"].stat().st_size > 0
    # decide() itself must be visible in the flame
    folded = paths["folded"].read_text()
    assert "core:decide" in folded
