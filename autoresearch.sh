#!/usr/bin/env bash
# Autoresearch harness: runs the Mads full-stack benchmark deterministically.
set -euo pipefail
cd "$(dirname "$0")"
python3 bench/run_bench.py
