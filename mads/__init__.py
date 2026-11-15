"""Mads (Modern Agent Design and Systems) reference implementation.

A deterministic, CPU-only simulation of the full stack from prompt to GPU,
mirroring the five CS2680 assignments:

- Lens    (mads.lens)       : token / cost / latency accounting, Mads-Lens
- Loop    (mads.agent_loop) : hand-rolled agent runtime, Mads-Loop
- Opt     (mads.opt)        : routing / context strategies, Mads-Opt
- Serve   (mads.scheduler, mads.kv_cache) : batching + paged KV cache, Mads-Serve
- Stack   (mads.scheduler)  : speculative decoding + full-stack config, Mads-Stack
"""

from .models import MODELS, ModelSpec
from .simclock import SimClock
from .kv_cache import PagedKVCache
from .scheduler import ModelRequest, ServingEngine
from .agent_loop import Agent, AgentConfig
from .lens import Lens
from .workload import PlanStep, Task, make_tasks
from .agent import run_workload
from .opt import baseline_config, route_by_step

__all__ = [
    "MODELS",
    "ModelSpec",
    "SimClock",
    "PagedKVCache",
    "ModelRequest",
    "ServingEngine",
    "Agent",
    "AgentConfig",
    "Lens",
    "PlanStep",
    "Task",
    "make_tasks",
    "run_workload",
    "baseline_config",
    "route_by_step",
]
