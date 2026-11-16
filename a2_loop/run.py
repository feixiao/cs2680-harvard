#!/usr/bin/env python3
"""Run the Mads-Loop agent runtime over the 12-task local set.

Usage:
  .venv/bin/python run.py --tag baseline \
      [--model qwen/qwen3.6-35b-a3b] [--base-url http://localhost:8081/v1] \
      [--tasks t01,t05] [--max-steps 30] [--ctx 32768] [--retries 5] \
      [--compact drop|llm] [--keep-recent 2] [--parallel-tools] \
      [--fault-rate 0] [--fault-hard] [--workdir /tmp/mads-a2-runs] \
      [--concurrency 1]

Prints per-task lines + METRIC aggregate lines; writes results/<tag>.json.
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from madsloop import Agent, AgentConfig, LLMClient
from madsloop.client import FaultyLLMClient
from madsloop.config import AgentConfig as _AC  # noqa
from tasks import TASKS, make_workspaces


def make_router(args):
    tiers = {"starter": args.tier_starter, "standard": args.tier_standard,
             "expert": args.tier_expert}
    def router(task, step_idx):
        tags = set(getattr(task, "tags", []))
        if tags & {"debug", "refactor"}:
            return tiers["expert"] if step_idx < 4 else tiers["standard"]
        if step_idx == 0:
            return tiers["standard"]
        return tiers["starter"] if tags & {"file", "data"} else tiers["standard"]
    return router


def parse_endpoints(spec: str) -> dict:
    out = {}
    for pair in filter(None, spec.split(",")):
        name, url = pair.split("=")
        out[name.strip()] = url.strip().rstrip("/")
    return out


def build_config(args) -> AgentConfig:
    cfg = AgentConfig(
        base_url=args.base_url,
        model=args.model,
        max_steps=args.max_steps,
        max_ctx_tokens=args.ctx,
        keep_recent=args.keep_recent,
        compact=args.compact,
        max_retries=args.retries,
        parallel_tools=args.parallel_tools,
        model_endpoints=parse_endpoints(args.endpoints),
        seed=args.seed,
    )
    if args.router == "heuristic":
        cfg.router = make_router(args)
    return cfg


async def run_one(task, cfg: AgentConfig, workdir: str, tag: str,
                  client: LLMClient) -> dict:
    ws = make_workspaces(workdir, [task.id])[task.id]
    agent = Agent(task, client, cfg, str(ws))
    t0 = time.monotonic()
    res = await agent.run()
    wall = time.monotonic() - t0
    ok_check, why = task.check(ws) if task.check else (True, "")
    if res.ok and not ok_check:
        res.status = "FAILED_CHECK"   # agent stopped claiming done, check disagrees
    row = {
        "task": task.id,
        "agent_status": res.status,
        "check": ok_check,
        "solved": bool(res.ok and ok_check),
        "why": why[:200],
        "steps": len(res.steps),
        "retries": res.retries,
        "tool_calls": res.tool_calls,
        "tool_errors": res.tool_errors,
        "loop_breaks": res.loop_breaks,
        "input_tokens": res.usage.input_tokens,
        "output_tokens": res.usage.output_tokens,
        "cache_read_tokens": res.usage.cache_read_tokens,
        "total_tokens": res.usage.total,
        "cost_usd_equivalent": round(res.cost_usd, 6),
        "agent_seconds": round(res.seconds, 2),
        "wall_seconds": round(wall, 2),
        "final_head": res.final_answer[:160],
    }
    print(f"TASK {task.id} solved={int(row['solved'])} {res.status} "
          f"steps={len(res.steps)} retries={res.retries} "
          f"tok={res.usage.total} ${res.cost_usd:.5f} {wall:.1f}s :: {why[:100]}",
          flush=True)
    return row


async def main_async(args):
    cfg = build_config(args)
    client = LLMClient(base_url=cfg.base_url, model=cfg.model,
                       max_retries=cfg.max_retries, base_delay=cfg.base_delay,
                       max_delay=cfg.max_delay, timeout=cfg.request_timeout,
                       temperature=cfg.temperature, max_output_tokens=cfg.max_output_tokens,
                       seed=cfg.seed, model_endpoints=cfg.model_endpoints)
    if args.fault_rate > 0:
        client = FaultyLLMClient(client, fault_rate=args.fault_rate,
                                 rng=__import__("random").Random(args.seed),
                                 hard_fail=args.fault_hard)

    want = [w for w in args.tasks.split(",") if w]
    tasks = [t for t in TASKS if not want
             or any(t.id == w or t.id.startswith(w) for w in want)]
    if not tasks:
        sys.exit("no tasks matched --tasks %r" % args.tasks)
    workdir = os.path.join(args.workdir, args.tag)

    sem = asyncio.Semaphore(args.concurrency)
    async def go(i, t):
        async with sem:
            # each concurrent task gets its own client (usage accounting is per-client)
            c2 = LLMClient(base_url=cfg.base_url, model=cfg.model,
                           max_retries=cfg.max_retries, base_delay=cfg.base_delay,
                           max_delay=cfg.max_delay, timeout=cfg.request_timeout,
                           temperature=cfg.temperature,
                           max_output_tokens=cfg.max_output_tokens, seed=cfg.seed,
                           model_endpoints=cfg.model_endpoints)
            if args.fault_rate > 0:
                # per-task distinct seeds: a shared seed makes every task's
                # injection stream start identically (Random(0)'s first dozen
                # draws are all > 0.2 -> zero faults actually injected)
                import random as _random
                c2 = FaultyLLMClient(c2, fault_rate=args.fault_rate,
                                     rng=_random.Random(args.seed * 7919 + i),
                                     hard_fail=args.fault_hard)
            return await run_one(t, cfg, workdir, args.tag, c2)

    rows = await asyncio.gather(*[go(i, t) for i, t in enumerate(tasks)])

    n = len(rows)
    solved = sum(r["solved"] for r in rows)
    agg = {
        "tag": args.tag,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "max_steps": cfg.max_steps,
        "max_ctx_tokens": cfg.max_ctx_tokens,
        "compact": cfg.compact,
        "keep_recent": cfg.keep_recent,
        "parallel_tools": cfg.parallel_tools,
        "concurrency": args.concurrency,
        "fault_rate": args.fault_rate,
        "tasks": n,
        "solved": solved,
        "success_rate": round(solved / n, 4),
        "total_tokens": sum(r["total_tokens"] for r in rows),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
        "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows),
        "retries": sum(r["retries"] for r in rows),
        "tool_calls": sum(r["tool_calls"] for r in rows),
        "tool_errors": sum(r["tool_errors"] for r in rows),
        "loop_breaks": sum(r["loop_breaks"] for r in rows),
        "total_cost_usd_equivalent": round(sum(r["cost_usd_equivalent"] for r in rows), 6),
        "wall_seconds": round(sum(r["wall_seconds"] for r in rows), 2),
        "per_task": rows,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for k in ("solved", "tasks"):
        print(f"METRIC {k}={agg[k]}")
    print(f"METRIC success_rate={agg['success_rate']}")
    print(f"METRIC total_tokens={agg['total_tokens']}")
    print(f"METRIC cache_read_tokens={agg['cache_read_tokens']}")
    print(f"METRIC retries={agg['retries']}")
    print(f"METRIC cost_usd_equivalent={agg['total_cost_usd_equivalent']}")
    print(f"METRIC wall_seconds={agg['wall_seconds']}")

    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"), exist_ok=True)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", f"{args.tag}.json")
    with open(out, "w") as f:
        json.dump(agg, f, indent=2)
    print(f"# results -> {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    p.add_argument("--model", default="qwen3.8-27b-splash")
    p.add_argument("--base-url", default="http://localhost:1234/v1")
    p.add_argument("--tasks", default="")
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument("--ctx", type=int, default=32768)
    p.add_argument("--retries", type=int, default=5)
    p.add_argument("--compact", choices=["drop", "llm"], default="drop")
    p.add_argument("--keep-recent", type=int, default=2)
    p.add_argument("--parallel-tools", action="store_true")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--router", choices=["off", "heuristic"], default="off",
                   help="per-step model routing (Mads-Opt lever)")
    p.add_argument("--tier-starter", default="qwen2.5-1.5b-instruct")
    p.add_argument("--tier-standard", default="qwen/qwen3.6-35b-a3b")
    p.add_argument("--tier-expert", default="qwen3.8-27b-splash")
    p.add_argument("--endpoints", default="",
                   help="model=http://host:port/v1[,model2=url2] for multi-engine routing")
    p.add_argument("--fault-rate", type=float, default=0.0)
    p.add_argument("--fault-hard", action="store_true")
    p.add_argument("--workdir", default="/tmp/mads-a2-runs")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
