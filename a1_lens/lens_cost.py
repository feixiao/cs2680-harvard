"""lens_cost — per-model price table and cost computation.

Prices are list USD per 1,000,000 tokens: (input, output).
Cache semantics follow Anthropic's: cache reads cost 10% of the input
price, cache creation costs 125% of the input price (5-minute ephemeral
writes; the older 1h write multiplier of 2x is folded in when the usage
dict reports the breakdown).

Model names in real Claude Code JSONL come in many flavors:
  - "claude-sonnet-4-5" / "claude-sonnet-4-5-20250929"  (Anthropic)
  - "lmstudio/qwen3.8-27b-splash"                      (local LM Studio)
  - "antigravity/claude-sonnet-4-6"                   (routed through a gateway)
  - "magpie/opencode-zen-free/deepseek-v4.1-flash-free"
  - "<synthetic>"                                     (Claude Code's own injected lines)

Unknown model  ->  price_unknown=True, cost 0 (per brief).
Local vendor prefixes (lmstudio/ollama/...)  ->  cost 0, price_unknown=True,
but flagged "local" so the UI can say "local model, $0".
"""

import re

# name -> (input $/MTok, output $/MTok)
PRICES = {
    # Anthropic Opus 4.x
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4-1": (5.0, 25.0),
    "claude-opus-4-0": (5.0, 25.0),
    "claude-opus-4": (5.0, 25.0),
    "claude-opus-3": (15.0, 75.0),
    "claude-3-opus-20240229": (15.0, 75.0),
    # Anthropic Sonnet
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-0": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-3-7-sonnet-latest": (3.0, 15.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-sonnet-latest": (3.0, 15.0),
    # Anthropic Haiku
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
    # Claude 2.x
    "claude-2-1": (8.0, 24.0),
    "claude-2-0": (11.0, 32.0),
    "claude-2": (11.0, 32.0),
    "claude-3": (0.0, 0.0),  # placeholder; real 3.0 retired
    # Qwen (DashScope international list prices, approx)
    "qwen-max": (1.6, 6.4),
    "qwen-plus": (0.4, 1.2),
    "qwen-turbo": (0.08, 0.4),
    "qwen3-235b-a22b": (0.2, 1.6),
    "qwen3-32b": (0.06, 0.4),
    "qwen3-30b-a3b": (0.03, 0.3),
    "qwen3-14b": (0.02, 0.2),
    # DeepSeek
    "deepseek-v4.1-flash-free": (0.0, 0.0),
    "deepseek-v3.1": (0.55, 2.2),
    "deepseek-v3": (0.27, 1.1),
    "deepseek-r1": (0.55, 2.2),
    # OpenAI
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "o3": (2.0, 8.0),
    "o4-mini": (1.1, 4.4),
    # Google
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.3, 2.5),
    "gemini-2.0-flash": (0.1, 0.4),
}

# Suffix fallback: when the normalized name isn't an exact match, try
# matching a trailing "model family" token, e.g. ".../claude-sonnet-4-5-20250929"
# -> "claude-sonnet-4-5".
_SUFFIX_RE = re.compile(r"(claude-[a-z0-9.-]+|qwen[a-z0-9.-]*|deepseek[a-z0-9.-]*|gpt-[a-z0-9.-]*|o\d-[a-z0-9.-]*|gemini-[a-z0-9.-]*|-20\d{6})")

# vendor prefixes that mean "served locally / free"
LOCAL_PREFIXES = ("lmstudio/", "ollama/", "local/", "openwebui/", "vllm/",
                  "lm-studio/", "llama-cpp/", "mlx/")

DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def normalize_model(name):
    """Return (normalized_name, is_local)."""
    if not name:
        return "", False
    n = name.strip()
    if n == "<synthetic>":
        return "<synthetic>", False
    low = n.lower()
    if low.startswith(LOCAL_PREFIXES):
        return low, True
    # strip gateway prefixes: "antigravity/claude-sonnet-4-6" -> "claude-sonnet-4-6"
    if "/" in low:
        tail = low.rsplit("/", 1)[-1]
        if tail in PRICES or _SUFFIX_RE.search(tail):
            low = tail
    # strip a trailing date suffix: claude-3-5-sonnet-20241022
    low = DATE_SUFFIX_RE.sub("", low)
    return low, False


def price_for(model):
    """Return (input_price, output_price, price_unknown, is_local, matched_name)."""
    norm, is_local = normalize_model(model)
    if norm == "<synthetic>":
        return 0.0, 0.0, True, False, "<synthetic>"
    if is_local:
        return 0.0, 0.0, True, True, norm
    if "free" in norm:  # explicit free tier
        return 0.0, 0.0, True, False, norm
    if norm in PRICES:
        p = PRICES[norm]
        return p[0], p[1], False, False, norm
    # suffix match
    m = _SUFFIX_RE.search(norm)
    if m:
        cand = m.group(1)
        cand = DATE_SUFFIX_RE.sub("", cand)
        if cand in PRICES:
            p = PRICES[cand]
            return p[0], p[1], False, False, cand
    return 0.0, 0.0, True, False, norm


def cost_for_usage(usage, model):
    """Compute (cost_usd, price_unknown, is_local, tokens) for one API call.

    `usage` is the assistant message.usage dict (Anthropic shape).
    tokens: {"input","output","cache_read","cache_create","thinking"}
    """
    usage = usage or {}
    inp = _num(usage.get("input_tokens"))
    out = _num(usage.get("output_tokens"))
    cr = _num(usage.get("cache_read_input_tokens"))
    cc = _num(usage.get("cache_creation_input_tokens"))
    th = _num((usage.get("output_tokens_details") or {}).get("thinking_tokens"))

    in_p, out_p, unknown, local, matched = price_for(model)
    # 1h cache creation writes cost 2x base; default to 1.25x (5m ephemeral)
    cc_cost = cc * in_p * 1.25
    cc1h = _num(((usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens")))
    cc5m = _num(((usage.get("cache_creation") or {}).get("ephemeral_5m_input_tokens")))
    if cc1h or cc5m:  # use the refined breakdown when available
        cc_cost = cc1h * in_p * 2.0 + (cc - cc1h) * in_p * 1.25
    cost = (inp * in_p + cr * in_p * 0.1 + cc_cost + out * out_p) / 1_000_000.0
    tokens = {"input": inp, "output": out, "cache_read": cr,
              "cache_create": cc, "thinking": th}
    return cost, unknown, local, matched, tokens


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0
