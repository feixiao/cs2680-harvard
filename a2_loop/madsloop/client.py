"""OpenAI-compatible chat client with structured tools and fault tolerance.

Retry policy: transient failures (timeouts, 429, 5xx, empty/malformed
completions) retry with exponential backoff + jitter; permanent 4xx raise
FatalLLMError. Usage is recorded per call, including cache reads when the
server reports them.
"""

import asyncio
import json
import random
from dataclasses import dataclass, field

import httpx


class LLMError(Exception):
    pass


class RetryableLLMError(LLMError):
    pass


class FatalLLMError(LLMError):
    pass


@dataclass
class Usage:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw: str

    @property
    def key(self) -> str:
        return self.name + ":" + json.dumps(self.arguments, sort_keys=True)


@dataclass
class Completion:
    content: str
    tool_calls: list = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = ""


class LLMClient:
    def __init__(self, base_url="http://localhost:1234/v1", api_key="lmstudio",
                 model="qwen/qwen3.6-35b-a3b", max_retries=5, base_delay=0.4,
                 max_delay=20.0, timeout=300.0, temperature=0.2,
                 max_output_tokens=4096, seed=0, rng=None, model_endpoints=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.rng = rng or random.Random(seed)
        self.total_usage = Usage()
        self.retry_count = 0
        self.empty_completion_retries = 0
        self.model_endpoints = model_endpoints or {}

    def _base_for(self, model: str) -> str:
        return self.model_endpoints.get(model, self.base_url)

    async def chat(self, messages, tools=None, model=None,
                   client: httpx.AsyncClient | None = None) -> Completion:
        model = model or self.model
        body = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }
        if tools:
            body["tools"] = tools

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    r = await client.post(
                        f"{self._base_for(model)}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=body,
                    )
                except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                    raise RetryableLLMError(f"network: {type(e).__name__}") from e

                if r.status_code in (429,) or 500 <= r.status_code < 600:
                    raise RetryableLLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                if 400 <= r.status_code < 500:
                    raise FatalLLMError(f"HTTP {r.status_code}: {r.text[:300]}")

                try:
                    data = r.json()
                    choice = data["choices"][0]
                    msg = choice["message"]
                except Exception as e:
                    raise RetryableLLMError(f"malformed body: {r.text[:200]}") from e

                calls = []
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    raw = fn.get("arguments", "")
                    try:
                        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                        if not isinstance(args, dict):
                            raise ValueError("arguments not an object")
                    except Exception:
                        # Model emitted broken JSON in tool arguments: recoverable
                        # by telling the model, not by killing the run.
                        calls.append(ToolCall(tc.get("id", ""), fn.get("name", ""),
                                              {"_broken_json": raw[:400]}, raw))
                        continue
                    calls.append(ToolCall(tc.get("id", ""), fn.get("name", ""), args, raw))

                usage = Usage(
                    model=model,
                    input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                    output_tokens=data.get("usage", {}).get("completion_tokens", 0),
                    cache_read_tokens=(data.get("usage", {}).get("prompt_tokens_details", {})
                                       or {}).get("cached_tokens", 0),
                )
                self.total_usage.add(usage)
                if not msg.get("content") and not calls:
                    self.empty_completion_retries += 1
                    if self.empty_completion_retries > 2:
                        raise FatalLLMError("repeatedly empty completion")
                    raise RetryableLLMError("empty completion")
                self.retry_count += 0
                return Completion(msg.get("content") or "", calls, usage,
                                  choice.get("finish_reason", ""))
        finally:
            if owns_client:
                await client.aclose()

    async def backoff(self, attempt: int) -> None:
        d = min(self.max_delay, self.base_delay * (2 ** attempt))
        await asyncio.sleep(self.rng.uniform(0.5 * d, d))
        self.retry_count += 1


class FaultyLLMClient(LLMClient):
    """Wraps the real client and injects transient faults to test the loop's
    fault tolerance (the course's hidden tests do the same, on api.cs2680.com).

    fault_rate = probability any single call faults; faults are transient by
    construction: after k faults the call succeeds.
    """

    def __init__(self, inner: LLMClient, fault_rate: float, rng=None,
                 hard_fail: bool = False):
        # Inherit the full LLMClient state (backoff params, retry bookkeeping)
        # so the agent's retry loop works identically against this wrapper.
        super().__init__(base_url=inner.base_url, api_key=inner.api_key,
                          model=inner.model, max_retries=inner.max_retries,
                          base_delay=inner.base_delay, max_delay=inner.max_delay,
                          timeout=inner.timeout, temperature=inner.temperature,
                          max_output_tokens=inner.max_output_tokens,
                          seed=0, rng=rng, model_endpoints=inner.model_endpoints)
        self._inner = inner
        self._rng = rng or random.Random()
        self._fault_rate = fault_rate
        self._hard_fail = hard_fail
        self._pending_faults = 0
        self.injected = 0
        self.recovered = 0

    async def chat(self, messages, tools=None, model=None, client=None):
        if self._rng.random() < self._fault_rate:
            self.injected += 1
            # Transient: fail a bounded number of consecutive times, then
            # let the call through — exactly what a flaky network / 503 storm
            # looks like to the agent.
            self._pending_faults = min(3, self._pending_faults + 1)
        if self._pending_faults > 0:
            self._pending_faults -= 1
            raise RetryableLLMError("injected transient fault (503-style)")
        c = await self._inner.chat(messages, tools=tools, model=model, client=client)
        self.recovered += 1
        self.total_usage = self._inner.total_usage
        # NB: do NOT reset self.retry_count here — the agent owns that counter
        # (increments on each caught fault, harvests after each success).
        return c
