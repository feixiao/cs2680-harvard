"""Mads-Loop: a hand-rolled agent runtime for CS2680.

No vendor SDK: a structured-tool-calling loop on top of any OpenAI-compatible
endpoint (here: LM Studio). Sliding context window with optional compaction,
retry with backoff on transient failures, termination + loop detection.
"""

from .config import AgentConfig
from .client import LLMClient, Usage, FatalLLMError, RetryableLLMError
from .context import ContextManager
from .tools import ToolExecutor
from .agent import Agent, AgentResult

__all__ = [
    "AgentConfig", "LLMClient", "Usage", "FatalLLMError", "RetryableLLMError",
    "ContextManager", "ToolExecutor", "Agent", "AgentResult",
]
