#!/usr/bin/env python3
"""Mads-Opt experiment driver (CS2680 Assignment 3).

Runs the A2 agent runtime (a2_loop/run.py) with each optimization lever
in SEQUENCE — one run at a time, because all engines share this Mac's CPU/
memory and concurrent engine loads corrupt measurements.

Engine topology (must be up before starting):
  expert   qwen3.8-27b-splash     @ http://localhost:1234/v1  (LM Studio)
  standard 35B-A3B (path-named mlx model) @ http://localhost:8084/v1  (mlx-lm)
  starter  qwen2.5-1.5b-instruct  @ http://localhost:8082/v1  (mlx-lm)
Start with:  a3_opt/engines.sh start   (a4_serve venv)

Experiments (each = all 12 tasks, --concurrency 3):
  E0 baseline     single standard model, drop-window, 32k ctx
  E1 routing      3-tier heuristic routing (experts pay for hard steps)
  E2 compaction   LLM compaction, keep_recent 2, 16k ctx
  E3 parallel     parallel tool execution
  E4 ctx-shrink   16k ctx window (drop)
  E5 full-stack   routing + compaction + parallel + 16k ctx

Aggregate: results/<tag>.json -> comparison table (tokens / $-equiv /
latency / success) for the blog.

Usage:  a3_opt/.venv... actually:  a2_loop/.venv/bin/python a3_opt/experiments.py [E0 E1 ...]
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
A2 = os.path.join(HERE, "..", "a2_loop")
PY = os.path.join(A2, ".venv", "bin", "python")
# standard tier = the A2 engine (35B-A3B @8084, path-named model id)
STD_ID = "/Users/Shared/LLM_Models/lmstudio-community/Qwen3.6-35B-A3B-MLX-4bit"
ENDPOINTS = ("qwen2.5-1.5b-instruct=http://localhost:8082/v1,"
             "qwen3.8-27b-splash=http://localhost:1234/v1,"
             + STD_ID + "=http://localhost:8084/v1")
TIER_STANDARD = STD_ID

EXPERIMENTS = {
    "E0": dict(tag="E0_baseline", extra=[]),
    "E1": dict(tag="E1_routing", extra=["--router", "heuristic"]),
    "E2": dict(tag="E2_compact", extra=["--compact", "llm", "--keep-recent", "2", "--ctx", "16384"]),
    "E3": dict(tag="E3_parallel", extra=["--parallel-tools"]),
    "E4": dict(tag="E4_ctx16k", extra=["--ctx", "16384"]),
    "E5": dict(tag="E5_fullstack",
               extra=["--router", "heuristic", "--compact", "llm",
                      "--keep-recent", "2", "--ctx", "16384", "--parallel-tools"]),
}

# E0 must use the SAME model as the A2 baseline (27B @1234) so the lever
# deltas are measured against it; the routing tiers use the mlx engines.
DEFAULT_MODEL = "qwen3.8-27b-splash"
BASE_URL = "http://localhost:1234/v1"


def engines_up() -> bool:
    import http.client
    for port in (1234, 8082, 8084):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("GET", "/v1/models")
            if c.getresponse().status != 200:
                print(f"engine :{port} unhealthy"); return False
        except Exception as e:
            print(f"engine :{port} down ({e}); run a3_opt/engines.sh start"); return False
    print("all engines up")
    return True


def run_one(name: str) -> dict:
    spec = EXPERIMENTS[name]
    cmd = [PY, os.path.join(A2, "run.py"),
           "--tag", spec["tag"], "--model", DEFAULT_MODEL, "--base-url", BASE_URL,
           "--concurrency", "1", "--endpoints", ENDPOINTS,
           "--tier-standard", TIER_STANDARD, *spec["extra"]]
    print("== %s: %s" % (name, " ".join(cmd[2:])))
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=A2)
    dt = time.time() - t0
    print(proc.stdout[-1500:])
    if proc.returncode != 0:
        print(proc.stderr[-1500:])
    jpath = os.path.join(A2, "results", spec["tag"] + ".json")
    d = json.load(open(jpath))
    d["driver"] = name
    d["wall_s"] = round(dt, 1)
    return d


def aggregate(names):
    rows = []
    for n in names:
        jpath = os.path.join(A2, "results", EXPERIMENTS[n]["tag"] + ".json")
        d = json.load(open(jpath))
        rows.append([n, d["solved"], d["tasks"], d["success_rate"],
                     d["total_tokens"], d["cost_usd_equivalent"],
                     d.get("wall_seconds", 0), d.get("retries", 0),
                     d.get("fault_recovered", 0)])
    hdr = ["exp", "solved", "tasks", "succ", "tokens", "$-equiv", "lat_s", "retries", "faultrec"]
    print("%-8s %-7s %-6s %-5s %9s %8s %9s %8s %8s" % tuple(hdr))
    for r in rows:
        print("%-8s %-7s %-6d %-5.2f %9d %8.4f %9.1f %8d %8d" % tuple(r))


def run_sim():
    """Deterministic mads/ sweep of the same levers (E0-E5): fixed-seed
    token streams + simulated clock, 16-task workload, byte-identical runs.
    Needs no live engine - use it on machines that can't hold the models.
    Dollars here are simulated list prices: relative, not absolute."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mads import AgentConfig, baseline_config, make_tasks, route_by_step, run_workload
    exps = {
        "E0": AgentConfig(),
        "E1": AgentConfig(router=route_by_step, resident=["starter", "draft"]),
        "E2": AgentConfig(compaction=True, keep_recent=2, prefix_reuse=True, prefix_budget=3072),
        "E3": AgentConfig(concurrency=16, parallel_tools=True),
        "E4": AgentConfig(prefix_reuse=True, prefix_budget=3072),
        "E5": baseline_config(),
    }
    base = None
    print("%-4s %-34s %-9s %-6s %-9s %-6s %s" % (
        "exp", "config", "e2e_s", "speed", "cost$", "save", "solved"))
    for name, cfg in exps.items():
        m, lens = run_workload(make_tasks(16, seed=42), cfg)
        if base is None:
            base = (m["e2e_latency_s"], m["total_cost_usd"])
        solved = "%d/%d" % (m["tasks_completed"], m["n_tasks"])
        failed = [t.task_id for t in lens.tasks if t.status != "DONE"]
        print("%-4s %-34s %9.1f %6.1fx %9.4f %6.1fx %s%s" % (
            name, EXPERT_CFG_LABEL.get(name, name),
            m["e2e_latency_s"], base[0] / m["e2e_latency_s"],
            m["total_cost_usd"], base[1] / m["total_cost_usd"],
            solved, ("  failed=" + ",".join(failed)) if failed else ""))


EXPERT_CFG_LABEL = {
    "E0": "naive: all expert, serial",
    "E1": "3-tier routing, starter-resident",
    "E2": "compaction: keep 2, 3k prefix budget",
    "E3": "concurrency 16 + parallel tools",
    "E4": "prefix reuse, 3k budget",
    "E5": "all + speculative + TP8",
}


def main():
    if "--sim" in sys.argv:
        run_sim()
        return
    which = sys.argv[1:] or list(EXPERIMENTS)
    # E0 is the A2 baseline itself (same model/engine/tasks) — reuse it.
    reuse = os.path.join(A2, "results", "baseline.json")
    if os.path.exists(reuse):
        which = [w for w in which if w != "E0"]
        print("reusing A2 baseline.json as E0")
    if not engines_up():
        sys.exit(1)
    for n in which:
        run_one(n)
    agg = [n for n in (["E0"] if os.path.exists(reuse) else []) + which]
    aggregate(agg)


if __name__ == "__main__":
    main()
