"""Model registry: per-model cost, latency, and serving characteristics.

Prices are in $ per 1M tokens. Latencies are in ms per token for a single
in-flight request. ``local`` models are served by the course GPU (32 GB) and
participate in the paged KV cache; API models are opaque endpoints.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    local: bool
    prefill_ms_per_tok: float
    decode_ms_per_tok: float
    in_price: float      # $ / 1M prompt tokens (uncached)
    out_price: float     # $ / 1M completion tokens
    cache_in_price: float  # $ / 1M prompt tokens served from KV cache
    max_ctx: int
    weights_gb: float = 0.0
    kv_bytes_per_tok: int = 0  # 2(K+V) * layers * kv_heads * head_dim * dtype


EXPERT = ModelSpec(
    name="expert", local=False,
    prefill_ms_per_tok=0.10, decode_ms_per_tok=33.0,
    in_price=3.0, out_price=15.0, cache_in_price=0.30,
    max_ctx=200_000,
)

# 8B open weights, bf16: 32 layers, 8 kv heads, 128 head dim
STANDARD = ModelSpec(
    name="standard", local=True,
    prefill_ms_per_tok=0.08, decode_ms_per_tok=12.5,
    in_price=0.40, out_price=1.60, cache_in_price=0.08,
    max_ctx=32_768,
    weights_gb=16.0, kv_bytes_per_tok=128 * 1024,
)

# 3B open weights, bf16: 24 layers, 8 kv heads, 64 head dim
STARTER = ModelSpec(
    name="starter", local=True,
    prefill_ms_per_tok=0.03, decode_ms_per_tok=5.0,
    in_price=0.10, out_price=0.40, cache_in_price=0.02,
    max_ctx=32_768,
    weights_gb=6.0, kv_bytes_per_tok=65 * 1024,
)

# 0.5B draft model for speculative decoding: never routed to by the agent,
# it only supplies draft windows that the target model verifies in one step.
DRAFT = ModelSpec(
    name="draft", local=True,
    prefill_ms_per_tok=0.02, decode_ms_per_tok=1.5,
    in_price=0.0, out_price=0.0, cache_in_price=0.0,
    max_ctx=8192,
    weights_gb=1.0, kv_bytes_per_tok=8 * 1024,
)

MODELS = {"expert": EXPERT, "standard": STANDARD, "starter": STARTER, "draft": DRAFT}
