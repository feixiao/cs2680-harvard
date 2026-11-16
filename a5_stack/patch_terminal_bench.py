#!/usr/bin/env python3
"""Idempotency: make terminal-bench's CLI import on Python 3.14.

Python 3.14 (PEP 649) evaluates function annotations lazily, in the module's
current globals. terminal-bench 0.2.18 defines CLI command functions named
``list`` in ``terminal_bench/cli/tb/{runs,datasets}.py`` which shadow the
builtin ``list``; annotations like ``list[str] | None`` in *other* commands of
the same module (e.g. ``runs.create``) then fail to resolve when typer builds
the command tree, and every ``tb``/``tbench`` invocation dies with
"TypeError: 'function' object is not subscriptable".

Fix: rename the shadowing functions (keeping the ``list`` subcommand name via
an explicit ``name=`` kwarg). Re-applies safely after a pip reinstall.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PATCHES = [
    # (file, old, new)
    ("terminal_bench/cli/tb/runs.py",
     "@runs_app.command()\ndef list(",
     '@runs_app.command(name="list")\ndef list_runs('),
    ("terminal_bench/cli/tb/datasets.py",
     "@datasets_app.command()\ndef list(",
     '@datasets_app.command(name="list")\ndef list_datasets('),
]


def patch_site_packages(site_packages: Path) -> int:
    n = 0
    for rel, old, new in PATCHES:
        p = site_packages / rel
        if not p.exists():
            print(f"patch: {rel} not found (different layout?) — skipped",
                  file=sys.stderr)
            continue
        text = p.read_text()
        if new in text:
            continue  # already patched
        if old not in text:
            print(f"patch: pattern not found in {rel} — skipped",
                  file=sys.stderr)
            continue
        p.write_text(text.replace(old, new))
        n += 1
    return n


def main() -> int:
    spec = importlib.util.find_spec("terminal_bench")
    if spec is None or spec.origin is None:
        return 0  # terminal-bench not in this interpreter; nothing to do
    site_packages = Path(spec.origin).parent.parent
    patch_site_packages(site_packages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
