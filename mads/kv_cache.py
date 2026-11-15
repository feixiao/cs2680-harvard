"""Paged KV cache with content-addressed prefix reuse (vLLM-style).

Blocks hold ``BLOCK_TOKENS`` tokens. A block's key is derived from the model
name and the block's token content, so identical conversation prefixes across
requests (or across re-runs of the same task) hit the same blocks. Eviction is
FIFO when the GPU budget is exceeded; evicted prefixes must be re-prefilled.
"""

import hashlib

BLOCK_TOKENS = 16


def block_key(model_name: str, tokens) -> str:
    h = hashlib.md5(model_name.encode("ascii"))
    for t in tokens:
        h.update(t.to_bytes(4, "big"))
    return h.hexdigest()


def block_keys(model_name: str, tokens):
    """Split a token list into 16-token blocks (tail block may be short)."""
    keys = []
    for i in range(0, len(tokens), BLOCK_TOKENS):
        keys.append(block_key(model_name, tokens[i : i + BLOCK_TOKENS]))
    return keys


class PagedKVCache:
    def __init__(self, budget_bytes: int):
        self.budget = int(budget_bytes)
        self.blocks = {}      # key -> bytes in use
        self.order = []       # FIFO insertion order of keys
        self.used = 0
        self.peak = 0.0
        self.hit_tokens = 0
        self.miss_tokens = 0

    def lookup(self, keys):
        """Number of leading cached blocks (0..len(keys))."""
        n = 0
        for k in keys:
            if k in self.blocks:
                n += 1
            else:
                break
        return n

    def cached_tokens(self, keys, prompt_len: int) -> int:
        toks = self.lookup(keys) * BLOCK_TOKENS
        toks = min(toks, prompt_len)
        self.hit_tokens += toks
        self.miss_tokens += prompt_len - toks
        return toks

    def materialize(self, keys, bytes_per_block) -> None:
        """Ensure all blocks resident, evicting FIFO as needed."""
        for k, b in zip(keys, bytes_per_block):
            if k in self.blocks:
                continue
            self._evict(b)
            self.blocks[k] = b
            self.order.append(k)
            self.used += b
        if self.used > self.peak:
            self.peak = self.used

    def _evict(self, need: int) -> None:
        while self.order and self.used + need > self.budget:
            k = self.order.pop(0)
            self.used -= self.blocks.pop(k)
