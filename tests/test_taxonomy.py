"""Slice 023 — test taxonomy enforcement.

The taxonomy lives in docs/campaign-i/023-test-taxonomy-rebuild.md.
This test keeps it honest: every test module must belong to exactly
one category, and marked modules must carry the matching
``pytestmark``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

TESTS = Path(__file__).resolve().parent
DOC = (TESTS.parent / "docs" / "campaign-i"
       / "023-test-taxonomy-rebuild.md")

CATEGORIES = {"unit", "integration", "slow", "gate"}


def _doc_table():
    text = DOC.read_text(encoding="utf-8")
    mapping = {}
    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "Category":
            continue
        category, _, _, files = cells
        if category not in CATEGORIES:
            continue
        for name in re.split(r",\s*", files):
            name = name.strip("` ")
            if name:
                mapping[name] = category
    return mapping


def _module_marks():
    marks = {}
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = set()
        for node in tree.body:
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                            for t in node.targets)):
                src = ast.get_source_segment(path.read_text(), node) or ""
                for cat in CATEGORIES - {"unit"}:
                    if cat in src:
                        found.add(cat)
        marks[path.stem] = found
    return marks


def test_every_test_module_has_exactly_one_category():
    table = _doc_table()
    modules = {p.stem for p in TESTS.glob("test_*.py")}
    assert set(table) == modules, (
        f"taxonomy doc mismatch — missing: {sorted(modules - set(table))}, "
        f"extra: {sorted(set(table) - modules)}")


def test_marks_match_the_doc():
    table = _doc_table()
    marks = _module_marks()
    problems = []
    for mod, category in sorted(table.items()):
        marked = marks[mod]
        if category == "unit":
            if marked:
                problems.append(f"{mod}: unit file carries {marked}")
        elif marked != {category}:
            problems.append(
                f"{mod}: doc says {category}, module marks {marked or 'none'}")
    assert not problems, problems


def test_conftest_fixtures_import_cleanly():
    import tests.conftest as cf
    assert hasattr(cf, "StubBackend")
    assert hasattr(cf, "gate_with_stub")
