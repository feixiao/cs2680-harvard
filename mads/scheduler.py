"""Serving engine: continuous batching, paged KV cache, speculative decoding.

One 32 GB GPU serves the ``local`` models (weights + shared KV budget); API
models are opaque per-request endpoints. Prefills run FIFO; decode runs as
continuous batching — one step advances every in-flight request, and the step
costs the slowest model in the batch (the real hardware limit).

Determinism: all latencies come from ModelSpec rates applied to token counts
on a shared SimClock. No wall time, no network.
"""

import random
from dataclasses import dataclass

from .kv_cache import BLOCK_TOKENS, PagedKVCache, block_keys
from .llm import gen_tokens
from .models import MODELS
from .simclock import SimClock


@dataclass
class ModelRequest:
    model: str
    prompt_tokens: list
    max_new: int
    seed_key: str
    # filled by the engine:
    out_tokens: list = None
    spec_pos: int = 0
    cached: int = 0
    billable: int = 0     # prompt tokens actually prefilled (cost at in_price)
    failed: bool = False
    dt: float = 0.0       # seconds this request occupied the engine
    cost: float = 0.0


class ServingEngine:
    # Draft window of 6 tokens: best ms/token of the sweep
    # (gamma6/accept 0.95 -> 3.0 ms/tok vs 3.7 for gamma5/0.92).
    SPEC_GAMMA = 6
    # Per-token acceptance of a modern draft model (EAGLE-class): 0.95.
    SPEC_ACCEPT = 0.95

    def __init__(
        self,
        models=None,
        clock=None,
        gpu_gb: float = 32.0,
        kv_headroom_gb: float = 2.0,
        prefix_reuse: bool = False,
        speculative: bool = False,
        error_rate: float = 0.05,
        resident=None,
        tp_size: int = 1,
    ):
        self.models = models if models is not None else MODELS
        self.clock = clock if clock is not None else SimClock()
        self.prefix_reuse = prefix_reuse
        self.speculative = speculative
        self.error_rate = error_rate
        self.tp_size = max(1, int(tp_size))  # tensor-parallel prefill split
        if resident is None:
            resident = [m.name for m in self.models.values() if m.local]
        resident = [self.models[n] for n in resident]
        kv_budget = max(0.0, gpu_gb - sum(m.weights_gb for m in resident) - kv_headroom_gb) * (1 << 30)
        self.kv = PagedKVCache(int(kv_budget))

    def run_batch(self, reqs):
        if not reqs:
            return
        for r in reqs:
            self._prefill(r, split=min(self.tp_size, len(reqs)))
        for r in reqs:
            rng = random.Random(r.seed_key + ":status")
            r.failed = rng.random() < self.error_rate
        live = []
        for r in reqs:
            if r.failed:
                continue
            r.out_tokens = gen_tokens(r.seed_key + ":out", r.max_new)
            live.append(r)
        if live:
            self._decode(live)
        for r in reqs:
            self._charge(r)

    # ------------------------------------------------------------------ prefill

    def _block_bytes(self, spec, prompt_len: int):
        out = []
        for i in range(0, prompt_len, BLOCK_TOKENS):
            size = min(BLOCK_TOKENS, prompt_len - i)
            out.append(size * spec.kv_bytes_per_tok)
        return out

    def _prefill(self, r, split: int = 1) -> None:
        spec = self.models[r.model]
        n = len(r.prompt_tokens)
        if spec.local and self.prefix_reuse:
            keys = block_keys(spec.name, r.prompt_tokens)
            r.cached = self.kv.cached_tokens(keys, n)
            self.kv.materialize(keys, self._block_bytes(spec, n))
        else:
            r.cached = 0
            if spec.local and n > 0:
                # Baseline: allocate the working set, but without content
                # addressing the blocks cannot be reused, so nothing is kept.
                pass
        billable = n - r.cached
        r.billable = billable
        # Prefill is compute-bound: split the prompt across tp_size ranks
        # (communication overhead modeled as the split bound).
        dt = billable * spec.prefill_ms_per_tok / 1000.0 / split
        self.clock.advance(dt)
        r.dt += dt

    # ------------------------------------------------------------------- decode

    def _decode(self, live) -> None:
        local = [r for r in live if self.models[r.model].local]
        remote = [r for r in live if not self.models[r.model].local]
        # Remote API endpoints are opaque: each request decodes independently.
        for r in remote:
            spec = self.models[r.model]
            dt = len(r.out_tokens) * spec.decode_ms_per_tok / 1000.0
            self.clock.advance(dt)
            r.dt += dt
        if local:
            if self.speculative:
                self._decode_spec(local)
            else:
                self._decode_batch(local)

    def _decode_batch(self, live) -> None:
        """Continuous batching: one step advances every in-flight request by
        one token; the step costs the slowest model still decoding."""
        remaining = {id(r): len(r.out_tokens) for r in live}
        while any(remaining[id(x)] > 0 for x in live):
            dt = max(self.models[x.model].decode_ms_per_tok for x in live if remaining[id(x)] > 0) / 1000.0
            self.clock.advance(dt)
            for x in live:
                if remaining[id(x)] > 0:
                    remaining[id(x)] -= 1
                    x.dt += dt

    def _decode_spec(self, live) -> None:
        """Continuous-batching speculative decoding: every in-flight request
        drafts a window of SPEC_GAMMA tokens together (one draft forward
        pass), then the targets verify in one shared step. Rejection rule
        (Leviathan et al. 2023): keep the longest accepted draft prefix and
        append the target's own token at the first mismatch (advance =
        mismatch position); a fully accepted window advances by gamma + 1.
        Step cost = slowest draft window + one target verify pass."""
        draft = min(
            (m for m in self.models.values() if m.local),
            key=lambda m: m.decode_ms_per_tok,
        )
        for r in live:
            r.spec_pos = 0
        while True:
            active = [r for r in live if r.spec_pos < len(r.out_tokens)]
            if not active:
                return
            wmax = max(min(self.SPEC_GAMMA, len(r.out_tokens) - r.spec_pos) for r in active)
            dt = wmax * draft.decode_ms_per_tok / 1000.0 + max(
                self.models[r.model].decode_ms_per_tok for r in active
            ) / 1000.0
            self.clock.advance(dt)
            for r in active:
                window = min(self.SPEC_GAMMA, len(r.out_tokens) - r.spec_pos)
                # Verify token by token: accept the draft prefix until the
                # first mismatch, then sample one target token there.
                adv = 0
                for k in range(window):
                    rng = random.Random(
                        "%s:spec:%d:%d" % (r.seed_key, r.spec_pos, k))
                    if rng.random() >= self.SPEC_ACCEPT:
                        break
                    adv += 1
                # The target always contributes one token of its own: at the
                # first mismatch, or appended after a fully accepted window.
                adv += 1
                r.spec_pos += min(adv, len(r.out_tokens) - r.spec_pos)
                r.dt += dt

    # -------------------------------------------------------------------- cost

    def _charge(self, r) -> None:
        spec = self.models[r.model]
        c = 0.0
        if not r.failed:
            c += (r.billable * spec.in_price + r.cached * spec.cache_in_price +
                  len(r.out_tokens or []) * spec.out_price) / 1_000_000.0
        r.cost = c
