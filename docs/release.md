# HugrGate 0.1.0 — release checklist

**Version:** 0.1.0 · **Status:** alpha · **Date:** 2026-10-09
**License:** Apache-2.0 (`LICENSE` at repo root)

This checklist must be fully green before tagging `v0.1.0` and
publishing. Items marked [x] are verified; [ ] need a human.

## 1. Naming search

- [ ] **PyPI:** confirm no published project named `hugrgate`
  (`pip index versions hugrgate` / https://pypi.org/project/hugrgate/).
- [ ] **GitHub:** confirm `hrabanazviking/RuneForgeAI-HugrGate` is the
  canonical home; no confusing forks squatting the name.
- [ ] **Trademark:** quick search (USPTO TESS / EUIPO / web) for
  "HugrGate" in software — no conflicting marks found as of 2026-10-09
  to the author's knowledge; formal search still open.
- [x] **In-repo:** no other package, module, or entry point claims the
  `hugrgate` / `hugrgate-server` names (`pyproject.toml` scripts are
  unique in this repo).

## 2. License audit

- [x] **Project license:** Apache-2.0 `LICENSE` present at repo root;
  `pyproject.toml` declares `license = { text = "Apache-2.0" }`.
- [x] **Dependency licenses** (audited 2026-10-09 from installed
  package metadata — all permissive, Apache-2.0-compatible):

  | Package | License |
  |---|---|
  | fastapi | MIT |
  | uvicorn | BSD-3-Clause |
  | httpx | BSD-3-Clause |
  | pyyaml | MIT |
  | numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
  | pytest | MIT |
  | scikit-learn | BSD-3-Clause |
  | scipy | BSD (OSI-approved) |
  | starlette | BSD-3-Clause |

  No GPL/AGPL copyleft in the dependency closure. Optional extras
  (`transformers`, `torch`, `llama-cpp-python`, `onnxruntime`) are not
  installed by default; re-audit when they are added to a lockfile.
- [ ] **Re-run** with `pip-licenses` (or `pipdeptree --license`) on the
  exact publish environment before uploading to PyPI.
- [x] **No vendored code:** every module is original; public methods
  re-implemented independently per `CLEAN_ROOM.md`.

## 3. Clean-room review

- [x] `CLEAN_ROOM.md` present: documents independent implementation
  from public mathematical methods (Platt scaling, PAV isotonic
  regression, temperature scaling, NLI, constrained decoding).
- [x] No model weights, datasets, or text copied from external
  benchmarks — `benchmarks/` templates are original (seeded generator
  in `benchmarks/build.py`).
- [ ] **Human review:** a second pair of eyes confirms no third-party
  code or prose slipped into `hugrgate/`, `benchmarks/`, `docs/`.

## 4. Quality gates

- [x] Full test suite green: `venv/bin/python -m pytest tests/`
  (322 passed on 2026-10-09).
- [x] Benchmark datasets build reproducibly:
  `venv/bin/python benchmarks/build.py` → byte-identical files,
  `sha256sum -c benchmarks/CHECKSUMS.sha256` passes.
- [x] Examples run: `service_roundtrip`, `benchmark_run`,
  `drift_watch`, `policy_playbook`, `client_policies`.
- [x] `pyproject.toml`: version 0.1.0, entry points
  (`hugrgate`, `hugrgate-server`), extras
  (`ml`, `onnx`, `nli`, `llm`, `server`, `bench`), alpha classifier.
- [ ] **Fresh-venv smoke test:** `pip install .` in a clean venv, then
  `hugrgate decide --spec … --state …` and one pytest run.
- [x] No `TODO`/`FIXME`/stub markers in shipped code
  (`grep -ri "todo\|fixme\|stub" hugrgate/` — clean).

## 5. Publishing steps (human)

1. `git fetch origin` — merge any of Volmarr's direct GitHub edits
   first (standing rule: never overwrite his changes; never force-push).
2. Update `CHANGELOG.md` "Unreleased" → `0.1.0` date if needed.
3. Commit, push, verify remote HEAD.
4. Tag `v0.1.0`, push tag.
5. Build: `python -m build`; check with `twine check dist/*`.
6. Upload to PyPI (or TestPyPI first).
7. Announce: README "Current Status" → alpha
   (**only Volmarr edits README.md** — repo rule).

## 6. Post-release

- [ ] Open issues for roadmap follow-ups (ladder router tuning,
  ONNX backend, model registry persistence).
- [ ] Schedule recalibration review of built-in baselines after real
  workloads land.
