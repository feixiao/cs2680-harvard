#!/usr/bin/env python3
"""Canonical benchmark: run the 16-task Mads workload through the full stack.

Deterministic: fixed workload seed, seeded token streams, simulated clock —
no network, no wall time, no live model. Prints METRIC lines consumed by the
autoresearch harness. Exits non-zero if the correctness gate fails (all
tasks must complete).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mads import baseline_config, make_tasks, run_workload  # noqa: E402


def main():
    t0 = time.time()
    metrics, lens = run_workload(make_tasks(16, seed=42), baseline_config())
    wall = time.time() - t0

    print("METRIC e2e_latency_s=%.3f" % metrics["e2e_latency_s"])
    print("METRIC total_cost_usd=%.4f" % metrics["total_cost_usd"])
    print("METRIC total_tokens=%d" % metrics["total_tokens"])
    print("METRIC prompt_tokens=%d" % metrics["prompt_tokens"])
    print("METRIC completion_tokens=%d" % metrics["completion_tokens"])
    print("METRIC cache_hit_rate=%.4f" % metrics["cache_hit_rate"])
    print("METRIC tasks_completed=%d" % metrics["tasks_completed"])
    print("METRIC retries=%d" % metrics["retries"])
    print("METRIC peak_kv_mb=%.1f" % metrics["peak_kv_mb"])
    print("# wall_s=%.3f (diagnostic only, not a scored metric)" % wall)

    if metrics["tasks_completed"] < metrics["n_tasks"]:
        print("CORRECTNESS GATE FAILED: %d/%d tasks completed"
              % (metrics["tasks_completed"], metrics["n_tasks"]))
        for s in lens.tasks:
            if s.status != "DONE":
                print("  failed: %s (%s)" % (s.task_id, s.status))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
