#!/usr/bin/env bash
# Fresh-clone install gauntlet (Gjallarbrú slice 477).
#
# Proves HugrGate installs and runs from a clean clone with no warm
# caches, no venv reuse, and no network beyond PyPI. Steps:
#
#   1. Clone the repo (or a given ref) into a fresh temp dir.
#   2. Create a brand-new venv with the running Python.
#   3. `pip install .` (project + runtime deps only, no extras).
#   4. Run the smoke probe: import the package, build a spec, run the
#      gate end to end, check the CLI entry point.
#   5. Report PASS/FAIL and clean up unless KEEP_CLONE=1.
#
# Usage:
#   tools/fresh_clone_install.sh [repo-url-or-path] [ref]
#
# Defaults: the current checkout's origin remote (or the local path),
# and HEAD. Set PIP_INDEX_URL to test against an internal mirror.
set -euo pipefail

REPO="${1:-$(git -C "$(dirname "$0")/.." config --get remote.origin.url 2>/dev/null || echo "$(cd "$(dirname "$0")/.." && pwd)")}"
REF="${2:-HEAD}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/hugrgate-fresh-XXXXXX")"

cleanup() {
    if [ "${KEEP_CLONE:-0}" != "1" ]; then
        rm -rf "$WORK"
    else
        echo "KEEP_CLONE=1: clone left at $WORK"
    fi
}
trap cleanup EXIT

echo "==> cloning $REPO ($REF) into $WORK"
git clone --quiet "$REPO" "$WORK/repo"
git -C "$WORK/repo" checkout --quiet "$REF"

echo "==> creating fresh venv"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip

echo "==> pip install . (no extras, no cache)"
"$WORK/venv/bin/pip" install --quiet --no-cache-dir "$WORK/repo"

echo "==> smoke probe"
"$WORK/venv/bin/python" "$WORK/repo/tools/install_smoke.py"

echo "==> console entry point"
"$WORK/venv/bin/hugrgate" --help >/dev/null

echo "PASS: fresh-clone install gauntlet"
