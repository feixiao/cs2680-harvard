"""Mads-Opt: cost & latency optimization policies.

This is the optimization surface of the full stack. The baseline routes
every step to the (slow, expensive) expert API model and runs everything
serialized; the levers live on AgentConfig and the router callable.
"""

from .agent_loop import AgentConfig
from .models import MODELS  # noqa: F401  (models available to policies)


def route_by_step(task, step_idx):
    """Routing policy: every step is served by the local standard 8B model.

    11x cheaper prompt, 2.6x faster decode than the expert API; the local
    GPU can also batch these requests continuously."""
    return "standard"


def baseline_config():
    """Optimized full stack: all steps on local standard, all 16 tasks
    advance concurrently (continuous batching), parallel tool calls, and
    content-addressed KV prefix reuse across steps of a task."""
    return AgentConfig(
        router=route_by_step,
        concurrency=16,
        parallel_tools=True,
        compaction=False,
        prefix_reuse=True,
        speculative=False,
    )
