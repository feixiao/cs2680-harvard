"""Context window management: token budget, sliding drop, optional compaction.

The context is a list of STEPS: [system] + [user task] + steps, where a step
is one assistant message (possibly carrying tool_calls) plus its tool results.
Windowing drops whole steps (tool pairs stay intact) and, with compaction,
replaces old steps by a one-line digest of them.
"""

import json
from .config import AgentConfig


def estimate_tokens(text: str) -> int:
    # ~4 chars/token for code/English mix; good enough for budgeting.
    return max(1, len(text) // 4)


def msg_tokens(m: dict) -> int:
    c = m.get("content") or ""
    n = estimate_tokens(c)
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function", {})
        n += estimate_tokens(fn.get("name", "") + fn.get("arguments", ""))
    return n


class ContextManager:
    def __init__(self, system_prompt: str, task_text: str, config: AgentConfig):
        self.system = {"role": "system", "content": system_prompt}
        self.messages: list[dict] = [
            self.system,
            {"role": "user", "content": task_text},
        ]
        self.steps: list[dict] = []       # {"asst": msg, "tools": [msgs], "tokens": int}
        self.config = config
        self.dropped = 0
        self.compacted = 0

    def append_assistant(self, msg: dict) -> None:
        self.messages.append(msg)
        self.steps.append({"asst": msg, "tools": [], "tokens": msg_tokens(msg)})

    def append_tool_result(self, msg: dict) -> None:
        self.messages.append(msg)
        if self.steps:
            self.steps[-1]["tools"].append(msg)
            self.steps[-1]["tokens"] += msg_tokens(msg)

    def total_tokens(self) -> int:
        return sum(msg_tokens(m) for m in self.messages)

    def window(self) -> None:
        cfg = self.config
        budget = cfg.max_ctx_tokens
        keep = max(1, cfg.keep_recent)
        while self.total_tokens() > budget and len(self.steps) > keep:
            old = self.steps[1] if len(self.steps) > 1 else self.steps[0]
            if cfg.compact == "llm":
                digest = self._digest(old)
                # replace the step with a single summarized user message
                for m in [old["asst"], *old["tools"]]:
                    if m in self.messages:
                        self.messages.remove(m)
                self.messages.insert(len(self.messages) - len(self.steps) + 1 + self.steps.index(old),
                                     {"role": "user", "content": f"[earlier work]\n{digest}"})
                old["tokens"] = estimate_tokens(digest)
            else:
                for m in [old["asst"], *old["tools"]]:
                    if m in self.messages:
                        self.messages.remove(m)
                self.dropped += 1
            self.steps.remove(old)

    def _digest(self, step: dict) -> str:
        """Mechanical one-line digest of a step (no LLM round trip):
        'step N: tool(a) -> ok; tool(b) -> error' plus a tail of the assistant text."""
        parts = []
        for m in step["tools"]:
            name = None
            for tc in step["asst"].get("tool_calls") or []:
                if tc.get("id") == m.get("tool_call_id"):
                    name = tc.get("function", {}).get("name")
            c = (m.get("content") or "")
            err = "error" if c.startswith("Error") else "ok"
            parts.append(f"{name}->{err}")
        text = (step["asst"].get("content") or "").replace("\n", " ")[:120]
        return "; ".join(parts) + (f" | note: {text}" if text else "")

    def nudge(self, text: str) -> None:
        """Inject a corrective user message (loop detection, broken-args)."""
        self.messages.append({"role": "user", "content": text})
