"""All the knobs of the runtime (the Mads-Opt/Mads-Stack levers live here)."""

from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_SYSTEM = """You are a coding agent working inside a sandbox workspace directory.
Available tools: bash (run a shell command in the workspace), read, write, edit, glob, grep.
Paths are relative to the workspace; never leave it.
Work step by step: inspect with read/glob/grep, act with bash/write/edit, verify with bash.
When the task is fully done and verified, reply with a short final answer and call no tools."""

# Public list prices used only as an API-equivalent cost yardstick
# (local inference pays electricity, not tokens). USD per 1M tokens.
PRICES = {
    "qwen/qwen3.6-35b-a3b": {"in": 0.15, "out": 0.60},    # ~ Qwen3-30B-A3B tier
    # mlx-lm reports the model DIRECTORY PATH as the OpenAI model id
    "/Users/Shared/LLM_Models/lmstudio-community/Qwen3.6-35B-A3B-MLX-4bit":
        {"in": 0.15, "out": 0.60},
    "/Users/Shared/LLM_Models/mlx-community/Qwen2.5-1.5B-Instruct-4bit":
        {"in": 0.01, "out": 0.03},
    "qwen2.5-1.5b-instruct": {"in": 0.01, "out": 0.03},
    "qwen3.8-27b-splash": {"in": 1.25, "out": 10.0},      # ~ frontier-class
}


@dataclass
class AgentConfig:
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lmstudio"
    model: str = "qwen/qwen3.6-35b-a3b"

    max_steps: int = 30
    max_ctx_tokens: int = 32768
    keep_recent: int = 2          # steps kept verbatim when the window fires
    compact: str = "drop"         # "drop" = slide oldest step out; "llm" = summarize it
    compact_model: Optional[str] = None   # model used for "llm" compaction (defaults to model)

    max_retries: int = 5
    base_delay: float = 0.4
    max_delay: float = 20.0
    request_timeout: float = 300.0

    temperature: float = 0.2
    max_output_tokens: int = 4096
    parallel_tools: bool = False  # run the tool calls of one step concurrently

    system_prompt: str = DEFAULT_SYSTEM
    router: Optional[Callable] = None   # fn(task, step_idx) -> model (Mads-Opt lever)
    # model name -> base_url override (multi-engine routing; defaults to base_url)
    model_endpoints: dict = None
    seed: int = 0

    def __post_init__(self):
        if self.model_endpoints is None:
            self.model_endpoints = {}

    def step_model(self, task, step_idx: int) -> str:
        if self.router is not None:
            return self.router(task, step_idx)
        return self.model

    def cost_usd(self, usage) -> float:
        for name in (self.model, usage.model):
            if name in PRICES:
                p = PRICES[name]
                break
        else:
            # fuzzy: match on the model basename (paths, tags, repo prefixes)
            base = (usage.model or self.model or "").rsplit("/", 1)[-1].lower()
            p = next((v for k, v in PRICES.items()
                      if base and base in k.lower()), None)
        if p is None:
            return 0.0
        return (usage.input_tokens * p["in"] + usage.output_tokens * p["out"]) / 1_000_000
