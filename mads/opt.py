"""Mads-Opt: cost & latency optimization policies.

This is the optimization surface of the full stack. The baseline routes
every step to the (slow, expensive) expert API model and runs everything
serialized; the levers live on AgentConfig and the router callable.
"""

from .agent_loop import AgentConfig
from .models import MODELS  # noqa: F401  (models available to policies)


def route_by_step(task, step_idx):
    """Routing policy: every step is served by the local starter 3B model —
    30x cheaper prompt and 6.6x faster decode than the expert API. Only
    starter (+ the 0.5B draft) is kept GPU-resident, maximizing the KV
    budget; the 8B standard stays offloaded."""
    return "starter"


def baseline_config():
    """Optimized full stack: all steps on local starter, all 16 tasks
    advance concurrently (continuous batching), parallel tool calls,
    content-addressed KV prefix reuse, proactive compaction to a small
    prefix budget (caps KV footprint), speculative decoding with the
    0.5B draft model, and 8-way tensor-parallel prefill."""
    return AgentConfig(
        router=route_by_step,
        concurrency=16,
        parallel_tools=True,
        compaction=True,
        prefix_reuse=True,
        speculative=True,
        keep_recent=2,
        prefix_budget=3072,
        resident=["starter", "draft"],
        tp_size=8,
    )
