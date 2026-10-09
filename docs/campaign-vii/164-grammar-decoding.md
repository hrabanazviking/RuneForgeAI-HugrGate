# Slice 164 — Grammar-constrained decoding

## Skald (what already existed)
- Slice 152's `LlamaCppRuntime` already passes `grammar=` to
  llama.cpp (GBNF passthrough) and advertises `CAP_GRAMMAR`, but no
  fabric-level API built or validated grammars.

## Rúnhild (design)
`hugrgate/runtimes/grammar.py`: `Grammar` (frozen dataclass) with
builders — `from_gbnf` (explicit), `from_literals` (categorical
alternation, the constrained-decoding workhorse),
`from_choice` (literals + optional whitespace) — plus `gbnf_escape`.
`_check_gbnf` does syntactic honesty (balanced quotes/brackets, root
rule present, no empty alternatives); it is not a full GBNF parser
and says so. `GrammarConstrainedRuntime` wraps an inner runtime:
validates the grammar *before* spending inference, refuses
(`BackendError`) when inner lacks `CAP_GRAMMAR` instead of silently
generating unconstrained, and rejects conflicting grammar sources.

## Eldra (what was built)
- `hugrgate/runtimes/grammar.py` (new): `Grammar`,
  `GrammarConstrainedRuntime`, `gbnf_escape`.
- `tests/test_localrt_164_grammar.py` (new, 18 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_164_grammar.py -q` → 18 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; designed to pair with slice 165
  (JSON-schema → GBNF compilation targets `Grammar.from_gbnf`).

## Scribe
Commit `feat(gjallarbu-164): grammar-constrained decoding` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Generated GBNF against real llama.cpp grammar parser (accepted /
  behaves as intended, esp. `from_choice` whitespace form).
