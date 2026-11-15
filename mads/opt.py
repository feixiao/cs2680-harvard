"""Mads-Opt: cost & latency optimization policies.

This is the optimization surface of the full stack. The baseline routes
every step to the (slow, expensive) expert API model and runs everything
serialized; the levers live on AgentConfig and the router callable.
"""

from .agent_loop import AgentConfig
from .models import MODELS  # noqa: F401  (models available to policies)


def route_by_step(task, step_idx):
    """Baseline routing: everything goes to the expert API model."""
    return "expert"


def baseline_config():
    """The un-optimized full stack: serial tasks, serial tools, no cache
    reuse, no compaction, no speculation, all-expert routing."""
    return AgentConfig(
        router=route_by_step,
        concurrency=1,
        parallel_tools=False,
        compaction=False,
        prefix_reuse=False,
        speculative=False,
    )
