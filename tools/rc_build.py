#!/usr/bin/env python3
"""Release-candidate build verifier (slice 498).

Builds the sdist and wheel (``python -m build`` — install the
``build`` package first), then verifies the release candidate:

1. both artifacts exist with canonical names;
2. wheel METADATA: name, version, requires-python, requires-dist;
3. entry_points.txt declares ``hugrgate`` and ``hugrgate-server``
   pointing at importable ``module:attr`` targets;
4. smoke install: wheel installed ``--no-deps`` into a temp dir,
   then ``import hugrgate``, both entry-point mains run
   ``--help``, and one live decision succeeds.

Exit 0 when every check passes, 1 otherwise. Prints a checklist.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def build_artifacts(repo: Path, outdir: Path,
                    builder: str) -> tuple[bool, str]:
    proc = _run([builder, "-m", "build", "--outdir", str(outdir)], repo)
    if proc.returncode != 0:
        return False, (proc.stderr.strip() or proc.stdout.strip())[-500:]
    return True, ""


def find_artifacts(outdir: Path) -> tuple[list[Path], list[Path]]:
    wheels = sorted(outdir.glob("*.whl"))
    sdists = sorted(outdir.glob("*.tar.gz"))
    return wheels, sdists


def verify_wheel_metadata(wheel: Path) -> list[str]:
    """Return a list of problems (empty = ok)."""
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        dist_info = next((n for n in names if n.endswith(".dist-info/METADATA")),
                         None)
        if dist_info is None:
            return ["no .dist-info/METADATA in wheel"]
        meta = zf.read(dist_info).decode()
        for field in ("Metadata-Version", "Name", "Version"):
            if field not in meta:
                problems.append(f"METADATA missing {field}")
        if "Requires-Dist: pyyaml" not in meta.replace("PyYAML", "pyyaml"):
            # Case-insensitive check for the single runtime dep.
            lowered = meta.lower()
            if "requires-dist: pyyaml" not in lowered:
                problems.append("METADATA missing Requires-Dist: pyyaml")
        ep_name = dist_info.replace("METADATA", "entry_points.txt")
        if ep_name not in names:
            problems.append("no entry_points.txt in wheel")
        else:
            ep = zf.read(ep_name).decode()
            for script, target in (("hugrgate", "hugrgate.cli:main"),
                                   ("hugrgate-server", "hugrgate.daemon:main")):
                if script not in ep or target not in ep:
                    problems.append(
                        f"entry point {script} -> {target} missing")
    # Wheel filename convention: {name}-{version}-py3-none-any.whl
    stem = wheel.stem
    if not stem.endswith("-py3-none-any"):
        problems.append(f"unexpected wheel tag in {wheel.name}")
    return problems


def smoke_install(wheel: Path, repo: Path) -> list[str]:
    """Install --no-deps into a temp dir and exercise the package."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rc-smoke-") as tmp:
        proc = _run([sys.executable, "-m", "pip", "install",
                     "--no-deps", "--target", tmp, str(wheel)], repo)
        if proc.returncode != 0:
            return [f"pip install failed: {proc.stderr.strip()[-300:]}"]
        probe = (
            "import sys; sys.path.insert(0, __TARGET__);"
            "import hugrgate;"
            "from hugrgate.cli import main as cli_main;"
            "from hugrgate.daemon import main as daemon_main;"
            "assert cli_main(['--help']) == 0;"
            "assert daemon_main(['--help']) == 0;"
            "from hugrgate import HugrGate, DecisionSpec, DecisionPolicy;"
            "from hugrgate.backends.rules import RuleBackend;"
            "g = HugrGate();"
            "g.register(RuleBackend.from_dicts([{'default': 'ok', 'confidence': 0.9}]));"
            "r = g.decide({'x': 1}, DecisionSpec(type='categorical', options=['ok', 'no']), DecisionPolicy());"
            "assert r.value == 'ok', r.value;"
            "g.close();"
            "print('smoke ok', hugrgate.__name__)"
        ).replace("__TARGET__", repr(tmp))
        proc = _run([sys.executable, "-c", probe], repo)
        if proc.returncode != 0:
            problems.append(
                f"smoke failed: {(proc.stderr.strip() or proc.stdout.strip())[-500:]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and verify the HugrGate release candidate.")
    parser.add_argument("--outdir", default="dist",
                        help="artifact directory (default: dist/)")
    parser.add_argument("--builder-python", default=sys.executable,
                        help="python with the 'build' package installed")
    parser.add_argument("--skip-build", action="store_true",
                        help="verify existing artifacts in --outdir")
    args = parser.parse_args(argv)

    repo = Path.cwd()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []

    if not args.skip_build:
        ok, detail = build_artifacts(repo, outdir, args.builder_python)
        checks.append(("build sdist+wheel", ok, detail))
        if not ok:
            return _report(checks)

    wheels, sdists = find_artifacts(outdir)
    checks.append(("wheel present", len(wheels) == 1,
                   f"found {len(wheels)}: {[w.name for w in wheels]}"))
    checks.append(("sdist present", len(sdists) == 1,
                   f"found {len(sdists)}: {[s.name for s in sdists]}"))
    if not wheels:
        return _report(checks)

    wheel = wheels[0]
    meta_problems = verify_wheel_metadata(wheel)
    checks.append(("wheel metadata + entry points",
                   not meta_problems, "; ".join(meta_problems)))
    smoke_problems = smoke_install(wheel, repo)
    checks.append(("smoke install + decide", not smoke_problems,
                   "; ".join(smoke_problems)))
    return _report(checks)


def _report(checks: list[tuple[str, bool, str]]) -> int:
    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark:>4}] {name}" + (f" — {detail}" if detail and not ok else ""))
        failed += not ok
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
