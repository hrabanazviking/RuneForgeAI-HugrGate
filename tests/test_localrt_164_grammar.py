"""Slice 164 — grammar-constrained decoding.

Unit tests for ``hugrgate.runtimes.grammar``: GBNF builders,
validation, and the constraining wrapper.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import (
    CAP_GRAMMAR,
    FakeRuntime,
    GenerationOptions,
    GenerationResult,
)
from hugrgate.runtimes.grammar import (
    Grammar,
    GrammarConstrainedRuntime,
    gbnf_escape,
)

# -- gbnf_escape ---------------------------------------------------------------------

def test_gbnf_escape():
    assert gbnf_escape('say "hi"\n') == 'say \\"hi\\"\\n'
    assert gbnf_escape("a\\b") == "a\\\\b"
    assert gbnf_escape("a\tb") == "a\\tb"


# -- Grammar builders -------------------------------------------------------------------

def test_from_literals_builds_alternation():
    g = Grammar.from_literals(["yes", "no"])
    assert g.source == 'root ::= "yes" | "no"'
    assert g.root == "root"
    assert str(g) == g.source


def test_from_literals_escapes_values():
    g = Grammar.from_literals(['a"b', "c\\d"])
    assert '"a\\"b"' in g.source
    assert '"c\\\\d"' in g.source


def test_from_literals_rejects_empty_and_dupes():
    with pytest.raises(SpecError):
        Grammar.from_literals([])
    with pytest.raises(SpecError):
        Grammar.from_literals(["a", "a"])


def test_from_choice_adds_whitespace():
    g = Grammar.from_choice(["yes", "no"])
    assert "root-inner" in g.source
    assert '"yes" | "no"' in g.source


def test_from_choice_rejects_bad_whitespace():
    with pytest.raises(SpecError):
        Grammar.from_choice(["a"], whitespace="\n")


def test_from_gbnf_validates():
    g = Grammar.from_gbnf('root ::= "a" [a-z]*')
    assert g.source == 'root ::= "a" [a-z]*'


# -- validation ------------------------------------------------------------------------------

def test_rejects_empty_source():
    with pytest.raises(SpecError):
        Grammar.from_gbnf("   ")


def test_rejects_unterminated_string():
    with pytest.raises(SpecError, match="unterminated"):
        Grammar.from_gbnf('root ::= "abc')


def test_rejects_unbalanced_brackets():
    with pytest.raises(SpecError, match="unbalanced"):
        Grammar.from_gbnf('root ::= ("a"')
    with pytest.raises(SpecError, match="outside a class"):
        Grammar.from_gbnf('root ::= "a"]')
    with pytest.raises(SpecError, match="unterminated character class"):
        Grammar.from_gbnf('root ::= [a-z')


def test_rejects_missing_root_rule():
    with pytest.raises(SpecError, match="no 'root' rule"):
        Grammar.from_gbnf('other ::= "a"')


def test_rejects_empty_alternative():
    with pytest.raises(SpecError, match="empty alternative"):
        Grammar.from_gbnf('root ::= "a" | | "b"')


def test_custom_root_name():
    g = Grammar.from_gbnf('answer ::= "yes"', root="answer")
    assert g.root == "answer"


# -- GrammarConstrainedRuntime --------------------------------------------------------------------

class GrammarFake(FakeRuntime):
    name = "grammar-fake"

    def __init__(self):
        super().__init__(supports=frozenset({CAP_GRAMMAR, "generate"}))
        self.seen: list[GenerationOptions] = []

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self.seen.append(options or GenerationOptions())
        return super().generate(prompt, options)


def test_wrapper_forwards_grammar():
    inner = GrammarFake()
    rt = GrammarConstrainedRuntime(inner)
    grammar = Grammar.from_literals(["yes", "no"])
    out = rt.generate_constrained("Answer:", grammar,
                                  GenerationOptions(max_tokens=4))
    assert inner.seen[0].grammar == grammar.source
    assert out.finish_reason == "constrained"


def test_wrapper_validates_grammar_early():
    inner = GrammarFake()
    rt = GrammarConstrainedRuntime(inner)
    with pytest.raises(SpecError):
        rt.generate("Answer:",
                    GenerationOptions(grammar='root ::= "oops'))
    assert inner.seen == []  # inner never called


def test_wrapper_refuses_without_capability():
    inner = FakeRuntime()  # no CAP_GRAMMAR
    rt = GrammarConstrainedRuntime(inner)
    with pytest.raises(BackendError, match="does not advertise"):
        rt.generate("Answer:",
                    GenerationOptions(grammar='root ::= "a"'))


def test_wrapper_passthrough_without_grammar():
    inner = GrammarFake()
    rt = GrammarConstrainedRuntime(inner)
    out = rt.generate("hello")
    assert out.finish_reason == "stop"
    assert inner.seen[0].grammar is None


def test_generate_constrained_rejects_conflict():
    inner = GrammarFake()
    rt = GrammarConstrainedRuntime(inner)
    grammar = Grammar.from_literals(["a"])
    with pytest.raises(SpecError, match="conflicts"):
        rt.generate_constrained("p", grammar,
                                GenerationOptions(
                                    grammar='root ::= "b"'))


def test_wrapper_info_and_health():
    inner = GrammarFake()
    rt = GrammarConstrainedRuntime(inner)
    assert rt.info().name == "grammar-fake+grammar"
    assert CAP_GRAMMAR in rt.info().capabilities
    assert rt.health()["grammar_constrained"] is True
    assert rt.privacy()["remote"] is False
    rt.close()
