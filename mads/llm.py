"""Deterministic pseudo-LLM: stable token content for any (seed_key, count).

Token "content" is a stream of 30-bit ints. Content depends only on the seed
key, so a conversation prefix that has not changed produces identical tokens
every run — which is what makes content-addressed KV-cache prefix reuse
well-defined.
"""

import random


def gen_tokens(seed_key: str, n: int):
    """n deterministic pseudo-tokens for a logical message."""
    r = random.Random(seed_key)
    return [r.getrandbits(30) for _ in range(n)]


def msg_tokens(seed_key: str, n: int):
    return gen_tokens(seed_key, n)
