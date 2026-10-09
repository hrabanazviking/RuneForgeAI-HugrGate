"""Slice 443 — every cookbook recipe actually runs.

Extracts the fenced ```python blocks from docs/cookbook.md and
executes each one in a fresh namespace. A recipe that raises, or
a doc whose recipe count drifts, fails the suite. Marked slow:
the HTTP recipe starts a real daemon.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parent.parent
COOKBOOK = REPO / "docs" / "cookbook.md"
BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _recipes() -> list[str]:
    blocks = BLOCK_RE.findall(COOKBOOK.read_text(encoding="utf-8"))
    assert blocks, "cookbook has no python recipes"
    return blocks


def test_cookbook_lists_every_recipe():
    headings = re.findall(r"^## \d+\. ", COOKBOOK.read_text(encoding="utf-8"),
                          re.MULTILINE)
    assert len(_recipes()) == len(headings), (
        f"{len(_recipes())} recipes vs {len(headings)} headings")


def test_recipes_are_self_contained():
    for i, code in enumerate(_recipes()):
        assert "import" in code, f"recipe {i + 1} has no imports"


@pytest.mark.parametrize("index", range(len(_recipes())))
def test_recipe_runs(index):
    code = _recipes()[index]
    namespace: dict = {"__name__": f"recipe_{index + 1}"}
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    exec(compile(code, f"<cookbook recipe {index + 1}>", "exec"),
         namespace)
