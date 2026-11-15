"""The benchmark workload: 16 deterministic agentic tasks.

Each task is a fixed plan of tool steps plus a final answer (the course
baseline solves 16 of 26). Plans, token counts, and tool latencies are drawn
from a seeded RNG, so every run of the workload is identical. The mock model
follows the plan; only price and latency scale with which model serves it.
"""

import random
from dataclasses import dataclass

from .llm import gen_tokens

SYSTEM_TOKS = 1200
TOOLS_TOKS = 900

TOOL_PROFILES = {
    #        out tokens        latency ms
    "search": (300, 1500, 50, 300),
    "read":   (200, 2000, 30, 200),
    "edit":   ( 50,  200, 20, 150),
    "shell":  (100,  800, 100, 2000),
    "answer": (150,  600,  0,    0),
}


@dataclass
class PlanStep:
    tool: str
    n_calls: int           # tool invocations issued by this step
    assistant_toks: int    # model output for the step (action + args)
    tool_toks: int         # tokens per tool result
    tool_dt_ms: float      # per-call tool latency (result content is derived
                           # per call from the task/step seed in agent_loop)


@dataclass
class Task:
    task_id: str
    steps: list

    @property
    def system_tokens(self):
        return gen_tokens("sys:" + self.task_id, SYSTEM_TOKS)

    @property
    def tools_tokens(self):
        return gen_tokens("tools:core", TOOLS_TOKS)


def make_tasks(n: int = 16, seed: int = 42):
    tasks = []
    for i in range(n):
        tr = random.Random("task-%d" % i)
        n_steps = tr.randint(5, 14)
        steps = []
        for s in range(n_steps):
            tool = "answer" if s == n_steps - 1 else tr.choice(["search", "read", "edit", "shell"])
            lo_t, hi_t, lo_d, hi_d = TOOL_PROFILES[tool]
            tool_toks = tr.randint(lo_t, hi_t)
            tool_dt = tr.uniform(lo_d, hi_d)
            step = PlanStep(
                tool=tool,
                n_calls=1 if tool == "answer" else tr.choice([1, 1, 1, 2, 3]),
                assistant_toks=tr.randint(120, 520),
                tool_toks=tool_toks,
                tool_dt_ms=tool_dt,
            )
            steps.append(step)
        tasks.append(Task("task-%d" % i, steps))
    return tasks
