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


class Message:
    __slots__ = ("role", "tokens", "mid")

    def __init__(self, role: str, tokens, mid: int):
        self.role = role
        self.tokens = tokens
        self.mid = mid

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
        self.messages = [
            Message("system", task.system_tokens, 0),
            Message("tools", task.tools_tokens, 1),
        ]

    # ------------------------------------------------------------- context

    def _total(self):
        return sum(m.n for m in self.messages)

    def _window(self, max_ctx: int) -> None:
        """Keep the context under max_ctx. Baseline: drop oldest messages
        (never the system/tools pair). With compaction: fold the oldest
        tool results into fixed-size summaries instead."""
        while self._total() > max_ctx:
            if self.config.compaction:
                candidates = [m for m in self.messages if m.role == "tool" and m.n > 100]
                keep = len(self.messages) - len(self.messages[:2]) - self.config.keep_recent
                old = [m for m in self.messages[2 : 2 + keep] if m.role == "tool" and m.n > 100]
                if not old:
                    self._drop_oldest()
                    continue
                m = old[0]
                m.tokens = gen_tokens("summary:" + str(m.mid), 100)
            else:
                self._drop_oldest()

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
        self.lens.record_request(self.task_idx, self.request)
        if self.request.failed:
            self.attempt += 1
            if self.attempt > self.config.retry_limit:
                self.state = FAILED
                self.lens.set_status(self.task_idx, FAILED)
                return
            self.clock.advance(0.5 * (2 ** (self.attempt - 1)))  # backoff
            self.submit()
            return
        step = self.task.steps[self.step_idx]
        self.messages.append(Message("assistant", self.request.out_tokens, len(self.messages)))
        if step.tool == "answer":
            self.state = DONE
            self.lens.set_status(self.task_idx, DONE)
            return
        self.state = RUN_TOOLS

    def run_tools(self) -> None:
        step = self.task.steps[self.step_idx]
        dts = [step.tool_dt_ms for _ in range(step.n_calls)]
        if self.config.parallel_tools:
            self.clock.advance(max(dts) / 1000.0)
        else:
            self.clock.advance(sum(dts) / 1000.0)
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
