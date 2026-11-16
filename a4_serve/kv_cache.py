"""Content-addressed paged KV prefix cache for the mlx server patch.

The mlx server's `--prompt-cache` does whole-DOCUMENT caching (full file hash
-> skip all prefill). This module implements the course's finer-grained
version: the token stream is split into fixed-size blocks (16 tokens); each
block is addressed by a *chained* hash of its tokens (a block's hash depends
on all prefix blocks, so it identifies an exact prefix), and cached block
chains are reusable by any request sharing that prefix. Eviction is LRU when
the block budget is exceeded.

The server patch uses it like this:
    for a new request with token ids `ids`:
        n = cache.match_prefix(ids)          # longest cached prefix (tokens)
        # prefill only ids[n:] into the model; register blocks for ids[n:]
        cache.register(ids[n:])
    and reports the skip via the /metrics patch (prompt_cache_skip_tokens).

Thread-safe; no mlx imports (the mlx side only needs token ids).
"""
import collections
import struct
import zlib
from dataclasses import dataclass

BLOCK_SIZE = 16


@dataclass
class _Block:
    hash: int
    tokens: bytes        # packed token ids, 2 bytes each
    lru: float           # monotonically increasing timestamp
    refs: int = 1        # chain links (a shared prefix keeps its blocks alive)


class PagedKVCache:
    def __init__(self, max_blocks: int = 1024, block_size: int = BLOCK_SIZE,
                 max_tokens: int | None = None):
        self.block_size = block_size
        self.max_blocks = max_blocks
        self.max_tokens = max_tokens or max_blocks * block_size
        self._blocks: dict[int, _Block] = {}
        self._order = collections.OrderedDict()   # hash -> None, LRU order
        self._clock = 0.0
        self.hits = 0
        self.misses = 0
        self.skipped_tokens = 0
        self.prefilled_tokens = 0

    # -- hashing -----------------------------------------------------------
    @staticmethod
    def _pack(tokens) -> bytes:
        return b"".join(struct.pack(">H", t & 0xFFFF) for t in tokens)

    @classmethod
    def _block_hash(cls, tokens, prev_hash: int) -> int:
        return zlib.crc32(prev_hash.to_bytes(8, "big") + cls._pack(tokens)) & 0xFFFFFFFF

    def _chain(self, tokens: list[int]):
        """Yield (hash, slice) per block of `tokens`, chained from root."""
        h = 0
        for i in range(0, len(tokens), self.block_size):
            chunk = tokens[i:i + self.block_size]
            h = self._block_hash(chunk, h)
            yield h, chunk

    def register(self, tokens: list[int]) -> int:
        """Cache the block chain for `tokens` (full request prefix).
        Returns number of new blocks added. Evicts LRU past budget.

        Eviction is BOUNDED: a shared prefix block (refs>1) has one link
        removed per eviction pass instead of vanishing, so a cache full of
        hot shared blocks may sit slightly over budget rather than thrash.
        That mirrors the course's "FIFO eviction past budget" and keeps the
        loop termination-guaranteed (a true vLLM-style prefix tree with
        child counts is the principled upgrade; noted in the blog)."""
        added = 0
        prev = 0
        for i in range(0, len(tokens), self.block_size):
            chunk = tokens[i:i + self.block_size]
            h = self._block_hash(chunk, prev)
            prev = h
            self._clock += 1
            if h in self._blocks:
                b = self._blocks[h]
                b.refs += 1
                b.lru = self._clock
                self._order.move_to_end(h)
            else:
                self._blocks[h] = _Block(h, self._pack(chunk), self._clock)
                self._order[h] = None
                added += 1
        for _ in range(256):
            if (len(self._blocks) <= self.max_blocks
                    and self._kv_tokens() <= self.max_tokens):
                break
            h, _ = self._order.popitem(last=False)
            b = self._blocks.get(h)
            if b is None:
                continue
            if b.refs > 1:
                b.refs -= 1            # still referenced; keep, re-park at tail
                b.lru = self._clock
                self._order[h] = None  # was popped above; re-insert
            else:
                del self._blocks[h]
        return added

    def _kv_tokens(self) -> int:
        return sum(len(b.tokens) // 2 for b in self._blocks.values())

    def match_prefix(self, tokens: list[int]) -> int:
        """Length (in tokens) of the longest cached prefix of `tokens`."""
        n = 0
        for h, chunk in self._chain(tokens):
            if h not in self._blocks:
                break
            n += len(chunk)
            self._touch(h)
        if n:
            self.hits += 1
        else:
            self.misses += 1
        if n:
            self.skipped_tokens += n
        return n

    def _touch(self, h: int):
        self._clock += 1
        b = self._blocks.get(h)
        if b:
            b.lru = self._clock
            self._order.move_to_end(h)

    # -- introspection -----------------------------------------------------
    def stats(self) -> dict:
        n = self.hits + self.misses
        return {
            "blocks": len(self._blocks),
            "max_blocks": self.max_blocks,
            "kv_tokens_cached": sum(len(b.tokens) // 2 for b in self._blocks.values()),
            "prefix_hits": self.hits,
            "prefix_misses": self.misses,
            "hit_rate": (self.hits / n) if n else 0.0,
            "skipped_prefill_tokens": self.skipped_tokens,
            "prefill_savings_ratio": (
                self.skipped_tokens / max(1, self.skipped_tokens + self.prefilled_tokens)),
        }

    def record_prefill(self, n_tokens: int) -> None:
        self.prefilled_tokens += n_tokens
