"""Mads-Loop: a hand-rolled agent runtime.

Structured tool calls, context window management (sliding-window drop or
compaction), transient-error retry with backoff, and termination detection.
The agent talks to a ServingEngine; it never calls a vendor SDK directly.
"""

import random

from .llm import gen_tokens
from .models import MODELS
from .scheduler import ModelRequest

INIT, AWAIT_MODEL, RUN_TOOLS, DONE, FAILED = "INIT", "AWAIT_MODEL", "RUN_TOOLS", "DONE", "FAILED"


class AgentConfig:
    """Every tunable of the full stack lives here (the Mads-Opt/Mads-Stack levers)."""

    def __init__(
        self,
        router=None,
        concurrency: int = 1,
        parallel_tools: bool = False,
        compaction: bool = False,
        prefix_reuse: bool = False,
        speculative: bool = False,
        error_rate: float = 0.05,
        retry_limit: int = 3,
        keep_recent: int = 3,
        prefix_budget: int = None,
        resident=None,
        tp_size: int = 1,
    ):
        self.router = router if router is not None else (lambda task, step_idx: "expert")
        self.concurrency = concurrency
        self.parallel_tools = parallel_tools
        self.compaction = compaction
        self.prefix_reuse = prefix_reuse
        self.speculative = speculative
        self.error_rate = error_rate
        self.retry_limit = retry_limit
        self.keep_recent = keep_recent
        self.prefix_budget = prefix_budget  # tokens; proactive compaction cap
        self.resident = resident  # GPU-resident model names (KV budget sizing)
        self.tp_size = tp_size  # tensor-parallel degree for prefill


class Message:
    __slots__ = ("role", "tokens", "mid", "summarized")

    def __init__(self, role: str, tokens, mid: int):
        self.role = role
        self.tokens = tokens
        self.mid = mid
        self.summarized = False

    @property
    def n(self):
        return len(self.tokens)


class Agent:
    def __init__(self, task, task_idx, engine, config, lens, clock):
        self.task = task
        self.task_idx = task_idx
        self.engine = engine
        self.config = config
        self.lens = lens
        self.clock = clock
        self.state = INIT
        self.step_idx = 0
        self.attempt = 0
        self.request = None
        self.wait = 0.0  # clock time the driver must wait before the agent resumes
        self.messages = [
            Message("system", task.system_tokens, 0),
            Message("tools", task.tools_tokens, 1),
        ]

    # ------------------------------------------------------------- context

    def _total(self):
        return sum(m.n for m in self.messages)

    def _window(self, max_ctx: int) -> None:
        """Keep the context under budget. Without compaction: drop oldest
        messages (never the system/tools pair). With compaction: proactively
        summarize the oldest non-recent messages into fixed-size summaries so
        the working set stays inside ``prefix_budget`` (default: max_ctx),
        shrinking KV footprint and re-prefill cost."""
        budget = self.config.prefix_budget or max_ctx
        budget = max(budget, self.messages[0].n + self.messages[1].n)
        while self._total() > budget:
            if self.config.compaction and self._summarize_oldest():
                continue
            self._drop_oldest()

    def _summarize_oldest(self) -> bool:
        """Fold all but the most recent ``keep_recent`` conversation messages
        into 100-token summaries. Returns True if anything was summarized."""
        candidates = [m for m in self.messages[2:] if not m.summarized and m.n > 100]
        if len(candidates) <= self.config.keep_recent:
            return False
        for m in candidates[: -self.config.keep_recent]:
            m.tokens = gen_tokens("summary:%d" % m.mid, 100)
            m.summarized = True
        return True

    def _drop_oldest(self) -> None:
        if len(self.messages) > 2:
            self.messages.pop(2)

    # ---------------------------------------------------------------- steps

    def submit(self) -> None:
        step = self.task.steps[self.step_idx]
        model = self.config.router(self.task, self.step_idx)
        spec = MODELS[model]
        self._window(spec.max_ctx)
        prompt = []
        for m in self.messages:
            prompt.extend(m.tokens)
        self.request = ModelRequest(
            model=model,
            prompt_tokens=prompt,
            max_new=step.assistant_toks,
            seed_key="%s:%d:%d" % (self.task.task_id, self.step_idx, self.attempt),
        )
        self.state = AWAIT_MODEL

    def receive(self) -> None:
        """The engine finished the request. Record it and decide the next
        action. The decision is immediate (no clock); the driver then
        schedules the follow-up work — retry backoff or tool I/O — to
        become ready after its delay, running concurrently with other
        agents' GPU work on the shared clock."""
        self.lens.record_request(self.task_idx, self.request)
        self.wait = 0.0
        if self.request.failed:
            self.attempt += 1
            if self.attempt > self.config.retry_limit:
                self.state = FAILED
                self.lens.set_status(self.task_idx, FAILED)
                return
            self.wait = 0.5 * (2 ** (self.attempt - 1))  # backoff
            self.submit()  # retry the same step; ready after the backoff
            return
        step = self.task.steps[self.step_idx]
        self.messages.append(Message("assistant", self.request.out_tokens, len(self.messages)))
        if step.tool == "answer":
            self.state = DONE
            self.lens.set_status(self.task_idx, DONE)
            return
        self.state = RUN_TOOLS

    def tool_dt(self) -> float:
        """Time this agent's tool calls take. ``parallel_tools`` overlaps
        the calls of one agent; the tools of different agents overlap on
        the shared clock (independent I/O) — they never block the GPU."""
        step = self.task.steps[self.step_idx]
        dts = [step.tool_dt_ms for _ in range(step.n_calls)]
        return (max(dts) if self.config.parallel_tools else sum(dts)) / 1000.0

    def run_tools(self) -> None:
        """Append tool results and advance the step (pure bookkeeping, no
        clock). The tool I/O time elapses on the shared clock via the
        driver's schedule while the GPU keeps serving other agents."""
        step = self.task.steps[self.step_idx]
        for c in range(step.n_calls):
            toks = gen_tokens("%s:%d:call:%d" % (self.task.task_id, self.step_idx, c), step.tool_toks)
            self.messages.append(Message("tool", toks, len(self.messages)))
        self.step_idx += 1
        if self.step_idx >= len(self.task.steps):
            self.state = DONE
            self.lens.set_status(self.task_idx, DONE)
            return
        self.attempt = 0
        self.submit()
