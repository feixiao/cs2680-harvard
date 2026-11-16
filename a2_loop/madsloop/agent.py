"""The agent loop: submit -> model -> tool calls -> results -> submit, with
termination, loop detection, and per-step accounting.
"""

import asyncio
import time
from dataclasses import dataclass, field

from .client import LLMClient, Usage, FatalLLMError, RetryableLLMError
from .config import AgentConfig
from .context import ContextManager, msg_tokens
from .tools import ToolExecutor


@dataclass
class StepRecord:
    idx: int
    model: str
    tool_names: list = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    retries: int = 0
    seconds: float = 0.0
    content_head: str = ""


@dataclass
class AgentResult:
    task_id: str
    status: str            # DONE | FAILED_MAX_STEPS | FAILED_ERROR
    final_answer: str
    steps: list = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    tool_calls: int = 0
    tool_errors: int = 0
    retries: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    loop_breaks: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "DONE"


class Agent:
    def __init__(self, task, client: LLMClient, config: AgentConfig, workdir: str):
        self.task = task
        self.client = client
        self.config = config
        self.tools = ToolExecutor(workdir)
        self.ctx = ContextManager(config.system_prompt, task.prompt, config)

    async def _chat_with_retry(self, model: str) -> "object":
        """Chat with retry/backoff on transient failures. Raises FatalLLMError."""
        last = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await self.client.chat(
                    self.ctx.messages, tools=self.tools.schemas, model=model)
            except RetryableLLMError as e:
                last = e
                self.client.retry_count += 1
                await self.client.backoff(attempt)
        raise FatalLLMError(f"{self.config.max_retries} retries exhausted: {last}")

    async def run(self) -> AgentResult:
        cfg, res = self.config, AgentResult(task_id=self.task.id, status="FAILED_ERROR",
                                            final_answer="")
        t0 = time.monotonic()
        consecutive_same: dict[str, int] = {}
        try:
            for idx in range(cfg.max_steps):
                model = cfg.step_model(self.task, idx)
                t1 = time.monotonic()
                try:
                    comp = await self._chat_with_retry(model)
                except FatalLLMError as e:
                    res.status = "FAILED_ERROR"
                    res.final_answer = f"model error: {e}"
                    break

                res.steps.append(StepRecord(
                    idx=idx, model=model,
                    tool_names=[c.name for c in comp.tool_calls],
                    usage=comp.usage, retries=self.client.retry_count,
                    seconds=time.monotonic() - t1,
                    content_head=(comp.content or "")[:100],
                ))
                res.usage.add(comp.usage)
                res.retries += self.client.retry_count
                self.client.retry_count = 0

                # terminate: model stops calling tools
                if not comp.tool_calls:
                    self.ctx.append_assistant({"role": "assistant",
                                               "content": comp.content,
                                               "finish_reason": comp.finish_reason})
                    res.status = "DONE"
                    res.final_answer = comp.content or ""
                    break

                # record assistant step, then run its tools
                self.ctx.append_assistant(self._asst_msg(comp))

                if cfg.parallel_tools:
                    results = await asyncio.gather(
                        *[self.tools.run(c.name, c.arguments) for c in comp.tool_calls],
                        return_exceptions=True)
                else:
                    results = []
                    for c in comp.tool_calls:
                        results.append(await self.tools.run(c.name, c.arguments))

                for c, r in zip(comp.tool_calls, results):
                    text = r if isinstance(r, str) else f"Error: {r!r}"
                    if isinstance(r, str) and r.startswith("Error"):
                        res.tool_errors += 1
                    # broken-JSON tool args: the model must see what went wrong
                    if c.arguments.get("_broken_json") is not None:
                        text = "Error: your tool arguments were not valid JSON " \
                               f"({c.arguments['_broken_json'][:200]}). Emit valid JSON."
                    res.tool_calls += 1
                    self.ctx.append_tool_result({
                        "role": "tool", "tool_call_id": c.id, "content": text})

                # loop detection: identical call 3x in a row
                for c, r in zip(comp.tool_calls, results):
                    k = c.key
                    consecutive_same[k] = consecutive_same.get(k, 0) + 1
                    if consecutive_same[k] >= 3 and isinstance(r, str) \
                            and r.startswith("Error"):
                        self.ctx.nudge("You are repeating the same failing action. "
                                       "Stop. Re-read the task, inspect the current "
                                       "file state, and try a materially different approach.")
                        consecutive_same.clear()
                        res.loop_breaks += 1
                    elif not (isinstance(r, str) and r.startswith("Error")):
                        consecutive_same.clear()

                self.ctx.window()
            else:
                res.status = "FAILED_MAX_STEPS"
                res.final_answer = f"reached max_steps={cfg.max_steps}"
        except Exception as e:
            res.status = "FAILED_ERROR"
            res.final_answer = f"crash: {type(e).__name__}: {e}"

        res.seconds = time.monotonic() - t0
        res.cost_usd = cfg.cost_usd(res.usage)
        return res

    def _asst_msg(self, comp) -> dict:
        return {
            "role": "assistant",
            "content": comp.content,
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.name,
                                         "arguments": json_dumps(c.arguments)}}
                           for c in comp.tool_calls],
        }


def json_dumps(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
