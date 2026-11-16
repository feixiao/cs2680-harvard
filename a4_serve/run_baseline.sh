#!/bin/bash
# Mads-Serve baseline matrix (CS2680 A4):
#   reuse {on, off} x suite {A: shared prefix, B: random} x N {1, 4, 8}
#
# For each reuse mode the engine is restarted (fresh prompt cache), then
# suites A and B run against it while metrics.py samples /metrics every
# 0.2 s. Outputs land in results/ (metrics JSON, METRIC lines, per-request
# JSONL) and are later summarized into results/baseline.md by hand.
set -uo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
export HUGGINGFACE_HUB_OFFLINE=1

for REUSE in on off; do
  echo "==================== reuse=$REUSE ===================="
  REUSE=$REUSE ./serve.sh || { echo "engine failed to start"; break; }

  # suite A: 16 requests sharing a ~4k prefix
  rm -f /tmp/mads_stop_A
  $PY metrics.py --duration 0 --stop-file /tmp/mads_stop_A \
    --out results/metrics_A_$REUSE.json --label A_$REUSE &
  MPID=$!
  $PY bench_synth.py --suite A --reuse $REUSE --N 1,4,8 \
    --out-jsonl results/requests_A_$REUSE.jsonl \
    | tee results/metric_lines_A_$REUSE.txt
  touch /tmp/mads_stop_A

  # suite B: 16 random prompts, 100-4k in / 50-200 out
  rm -f /tmp/mads_stop_B
  $PY metrics.py --duration 0 --stop-file /tmp/mads_stop_B \
    --out results/metrics_B_$REUSE.json --label B_$REUSE &
  MPID=$!
  $PY bench_synth.py --suite B --reuse $REUSE --N 1,4,8 \
    --out-jsonl results/requests_B_$REUSE.jsonl \
    | tee results/metric_lines_B_$REUSE.txt
  touch /tmp/mads_stop_B

  wait $MPID || true
done

./serve.sh --stop
echo "baseline matrix complete"
