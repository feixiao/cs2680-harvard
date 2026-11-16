#!/usr/bin/env python3
"""Mads-Serve synthetic load client (CS2680 A4).

OpenAI-compatible load generator for the mlx-lm engine on port 8081.
Stdlib only (urllib); optionally uses a HuggingFace tokenizer (when run with
the a4 venv python) to build prompts of an exact token count — otherwise a
chars/3.2 heuristic is used.

Suites
  A "shared prefix": K=16 prompts, all sharing one ~4k-token stable prefix
    plus a ~100-token varied tail. Stress case for KV prefix reuse.
  B "random": varied prompt lengths 100-4k tokens, output 50-200 tokens.
    Stress case for continuous batching / chunked prefill.

For every (suite, N) point it records per-request TTFT / TPOT / e2e, aggregate
throughputs, and takes an engine /metrics snapshot before and after the point
(session counters are monotonic, so the difference is the point's engine-side
work). Emits METRIC key=value lines and a per-request JSONL.

The --reuse flag only labels results; the actual KV prefix-reuse switch is the
engine flag --prompt-cache-size (serve.sh REUSE=on|off).

Usage:
  python3 bench_synth.py --suite A --reuse on --N 1,4,8
  python3 bench_synth.py --suite both --reuse off --K 16 --seed 42 \
      --url http://127.0.0.1:8081 --out-jsonl results/requests_B_off.jsonl
"""

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODEL_DIR = (
    "/Users/Shared/LLM_Models/mlx-community/Qwen2.5-1.5B-Instruct-4bit"
)

# ~200 common English words; enough variety to avoid the model's EOS reflex.
WORDS = """
the of and to in a is that it was for on are with as at be this from or had
by but not his they said she have all will one when their what there we would
which can who an were you so no if how man men its now about up out other into
these work them then time year some could see than any day most only over after
also did my such like just more very much where very being each just new even
people still first both through much another too only back way little old large
next long two little small large great little big high small low good bad new
old rich poor large small light heavy fast slow open close move stop start
water fire earth wind air stone wood metal glass river mountain field forest
city house door window table chair book page letter word number name sound
light dark night morning evening season winter summer spring autumn cold warm
hot cool dry wet full empty half whole part piece line point circle square
triangle angle distance speed force power energy machine engine wheel
worker farmer doctor teacher student teacher scholar writer reader singer
market shop store bank road bridge street village country world nation
language story poem song dance music picture drawing painting writing reading
learning teaching thinking feeling wanting hoping wishing fearing loving
building making doing taking giving keeping finding losing winning playing
working living dying growing changing becoming helping leading following
singing dancing writing speaking thinking studying reading searching finding
"""
WORD_LIST = WORDS.split()


def make_tokenizer(model_dir):
    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(model_dir)

        class T:
            @staticmethod
            def encode(text):
                return tok(text, add_special_tokens=False).input_ids

        return T()
    except Exception as e:  # pragma: no cover - depends on environment
        print(f"WARNING: could not load tokenizer ({e}); "
              "falling back to chars/3.2 estimate", file=sys.stderr)

        class T:
            @staticmethod
            def encode(text):
                return list(range(max(1, len(text) // 3)))

        return T()


def make_text(rng, target, tok):
    """Build word-soup text of ~`target` tokens (deterministic for a seed)."""
    words = []
    while True:
        words.append(WORD_LIST[rng.randrange(len(WORD_LIST))])
        n = len(tok.encode(" ".join(words)))
        if n >= target * 1.06 or len(words) > 80000:
            break
    # Binary search word count for ~target tokens (token count is monotone
    # up to boundary re-merges of +/-1).
    lo, hi = 0, len(words)
    while lo < hi:
        mid = (lo + hi) // 2
        if len(tok.encode(" ".join(words[:mid]))) < target:
            lo = mid + 1
        else:
            hi = mid
    text = " ".join(words[:lo])
    n = len(tok.encode(text))
    while n < target and len(words) < lo + 512:
        words.append(WORD_LIST[rng.randrange(len(WORD_LIST))])
        text = " ".join(words)
        n = len(tok.encode(text))
    return text, len(tok.encode(text))


def build_suite_a(rng, tok, prefix_tokens):
    prefix, n_prefix = make_text(rng, prefix_tokens, tok)
    prompts = []
    for i in range(args.K):
        tail, n_tail = make_text(rng, 100, tok)
        content = prefix + "\n\n" + tail
        prompts.append(
            {
                "idx": i,
                "content": content,
                "prompt_tokens": len(tok.encode(content)),
                "max_tokens": 128,
                "temperature": 0.7,
            }
        )
    print(
        f"[bench] suite A: prefix={n_prefix} tokens "
        f"(target {prefix_tokens}), tail~100, prompt~"
        f"{prompts[0]['prompt_tokens']} tokens",
        file=sys.stderr,
    )
    return prompts


def build_suite_b(rng, tok, n_prompts):
    prompts = []
    for i in range(n_prompts):
        n_target = 100 + rng.randrange(0, 4000 - 100)
        content, n = make_text(rng, n_target, tok)
        prompts.append(
            {
                "idx": i,
                "content": content,
                "prompt_tokens": n,
                "max_tokens": 50 + rng.randrange(0, 200 - 50),
                "temperature": 0.8,
            }
        )
    print(
        f"[bench] suite B: {n_prompts} prompts, prompt tokens "
        f"min={min(p['prompt_tokens'] for p in prompts)} "
        f"max={max(p['prompt_tokens'] for p in prompts)} "
        f"mean={sum(p['prompt_tokens'] for p in prompts) // n_prompts}",
        file=sys.stderr,
    )
    return prompts


def get_metrics(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/metrics", timeout=10) as r:
            vals = {}
            for line in r.read().decode().splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    try:
                        vals[parts[0]] = float(parts[1])
                    except ValueError:
                        pass
            return vals
    except (urllib.error.URLError, OSError):
        return {}


def post_stream(url, body, timeout=1800):
    """POST /v1/chat/completions (streaming). Returns (record, sse_jsons)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    rec = {
        "ttft_ms": None,
        "tpot_ms": None,
        "e2e_ms": None,
        "gen_tokens": 0,
        "prompt_tokens": None,
        "cached_tokens": None,
        "finish": None,
        "error": None,
    }
    sse_jsons = []
    times = []
    first = None  # pre-init: an HTTP error before the stream must not
    # leave this unbound below
    te = t0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                sse_jsons.append(obj)
                choice = (obj.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                text = delta.get("content") or ""
                now = time.perf_counter()
                if text:
                    if first is None:
                        first = now
                    times.append(now)
                if choice.get("finish_reason"):
                    rec["finish"] = choice["finish_reason"]
                usage = obj.get("usage") or {}
                if usage.get("completion_tokens") is not None:
                    rec["gen_tokens"] = usage["completion_tokens"]
                if usage.get("prompt_tokens") is not None:
                    rec["prompt_tokens"] = usage["prompt_tokens"]
                if (usage.get("prompt_tokens_details") or {}).get(
                    "cached_tokens"
                ) is not None:
                    rec["cached_tokens"] = usage["prompt_tokens_details"][
                        "cached_tokens"
                    ]
            te = time.perf_counter()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        body = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                body = " body=" + e.read().decode(errors="replace")[:200]
            except Exception:
                pass
        rec["error"] = f"{type(e).__name__}: {e}{body}"
        te = time.perf_counter()

    if first is not None:
        rec["ttft_ms"] = (first - t0) * 1000.0
    if times:
        rec["e2e_ms"] = (te - t0) * 1000.0
        n_tok = rec["gen_tokens"] if rec["gen_tokens"] else len(times)
        if rec["gen_tokens"] is None:
            rec["gen_tokens"] = len(times)
        if n_tok > 1:
            rec["tpot_ms"] = (times[-1] - times[0]) * 1000.0 / (n_tok - 1)
    elif rec["error"] is None:
        rec["e2e_ms"] = (te - t0) * 1000.0
    return rec, sse_jsons


def run_point(suite, n, reuse, prompts, url, out_file, gpu):
    """Run one (suite, N) point; return summary dict + METRIC lines."""
    engine_pre = get_metrics(url)
    wall0 = time.perf_counter()
    records = []
    bodies = [
        {
            "model": "default_model",
            "messages": [{"role": "user", "content": p["content"]}],
            "max_tokens": p["max_tokens"],
            "temperature": p["temperature"],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        for p in prompts
    ]
    if n <= 1:
        for p, b in zip(prompts, bodies):
            rec, _ = post_stream(url, b)
            rec.update(suite=suite, N=n, reuse=reuse, idx=p["idx"],
                        requested_prompt_tokens=p["prompt_tokens"],
                        max_tokens=p["max_tokens"])
            records.append(rec)
    else:
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(post_stream, url, b) for b in bodies]
            for p, f in zip(prompts, futs):
                rec, _ = f.result()
                rec.update(suite=suite, N=n, reuse=reuse, idx=p["idx"],
                           requested_prompt_tokens=p["prompt_tokens"],
                           max_tokens=p["max_tokens"])
                records.append(rec)
    wall = time.perf_counter() - wall0
    engine_post = get_metrics(url)

    with out_file:
        for rec in records:
            out_file.write(json.dumps(rec) + "\n")

    ok = [r for r in records if r["error"] is None]
    ttfts = [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]
    tpots = [r["tpot_ms"] for r in ok if r["tpot_ms"] is not None]
    e2es = [r["e2e_ms"] for r in ok if r["e2e_ms"] is not None]
    prompt_tok = sum(r.get("prompt_tokens") or r["requested_prompt_tokens"]
                     for r in ok)
    gen_tok = sum(r.get("gen_tokens") or 0 for r in ok)

    def pct(v, q):
        v = sorted(v)
        if not v:
            return None
        k = max(0, min(len(v) - 1, int(round((len(v) - 1) * q))))
        return v[k]

    def d(name):
        a, b = engine_pre.get(name), engine_post.get(name)
        return None if a is None or b is None else b - a

    dv = lambda k: d("mlx_lm_" + k)
    enc = {
        "n": len(records),
        "ok": len(ok),
        "err": len(records) - len(ok),
        "ttft_p50": pct(ttfts, 0.5),
        "ttft_p95": pct(ttfts, 0.95),
        "ttft_max": max(ttfts) if ttfts else None,
        "tpot_p50": pct(tpots, 0.5),
        "tpot_p95": pct(tpots, 0.95),
        "e2e_p50": pct(e2es, 0.5),
        "e2e_p95": pct(e2es, 0.95),
        "wall_s": wall,
        "prompt_tok": prompt_tok,
        "gen_tok": gen_tok,
        "client_prompt_tok_s": prompt_tok / wall if wall else None,
        "client_gen_tok_s": gen_tok / wall if wall else None,
        "eng_prompt_tok": dv("prompt_tokens_total"),
        "eng_prompt_time_s": dv("prompt_time_seconds_total"),
        "eng_gen_tok": dv("generation_tokens_total"),
        "eng_decode_time_s": dv("decode_time_seconds_total"),
        "eng_prompt_tok_s": (
            dv("prompt_tokens_total") / dv("prompt_time_seconds_total")
            if dv("prompt_time_seconds_total") else None
        ),
        "eng_decode_tok_s": (
            dv("generation_tokens_total") / dv("decode_time_seconds_total")
            if dv("decode_time_seconds_total") else None
        ),
        "cache_hits": dv("prompt_cache_hits_total"),
        "cache_misses": dv("prompt_cache_misses_total"),
        "cache_reused_tokens": dv("prompt_cache_tokens_reused_total"),
        "paged_skip_tokens": dv("paged_kv_skipped_tokens_total"),
        "paged_prefill_tokens": dv("paged_kv_prefilled_tokens_total"),
        "cached_frac": (
            sum(r["cached_tokens"] for r in ok if r["cached_tokens"])
            / max(1, sum(r.get("prompt_tokens") or 0 for r in ok))
            if any(r.get("cached_tokens") for r in ok)
            else 0.0
        ),
        "kv_bytes_peak": max(
            (
                engine_pre.get("mlx_lm_prompt_cache_bytes", 0)
                + engine_pre.get("mlx_lm_kv_active_bytes", 0),
                engine_post.get("mlx_lm_prompt_cache_bytes", 0)
                + engine_post.get("mlx_lm_kv_active_bytes", 0),
            )
        )
        if engine_pre or engine_post
        else None,
    }
    f1 = lambda v: f"{v:.1f}" if v is not None else "na"
    f2 = lambda v: f"{v:.2f}" if v is not None else "na"
    lines = [
        f"METRIC suite={suite} N={n} reuse={reuse} gpu={gpu} "
        f"n={enc['n']} ok={enc['ok']} err={enc['err']} wall_s={f1(enc['wall_s'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} "
        f"ttft_ms_p50={f1(enc['ttft_p50'])} ttft_ms_p95={f1(enc['ttft_p95'])} "
        f"ttft_ms_max={f1(enc['ttft_max'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} "
        f"tpot_ms_p50={f2(enc['tpot_p50'])} tpot_ms_p95={f2(enc['tpot_p95'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} "
        f"e2e_ms_p50={f1(enc['e2e_p50'])} e2e_ms_p95={f1(enc['e2e_p95'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} "
        f"prompt_tok={enc['prompt_tok']} gen_tok={enc['gen_tok']} "
        f"client_prompt_tok_s={f1(enc['client_prompt_tok_s'])} "
        f"client_gen_tok_s={f1(enc['client_gen_tok_s'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} engine "
        f"prompt_tok={int(enc['eng_prompt_tok'] or 0)} "
        f"prompt_time_s={f2(enc['eng_prompt_time_s'])} "
        f"prompt_tok_s={f1(enc['eng_prompt_tok_s'])} "
        f"decode_tok={int(enc['eng_gen_tok'] or 0)} "
        f"decode_time_s={f2(enc['eng_decode_time_s'])} "
        f"decode_tok_s={f1(enc['eng_decode_tok_s'])}",
        f"METRIC suite={suite} N={n} reuse={reuse} cache "
        f"hits={int(enc['cache_hits'] or 0)} misses={int(enc['cache_misses'] or 0)} "
        f"reused_tokens={int(enc['cache_reused_tokens'] or 0)} "
        f"cached_frac={enc['cached_frac']:.3f} "
        f"paged_skip={int(enc['paged_skip_tokens'] or 0)} "
        f"paged_prefill={int(enc['paged_prefill_tokens'] or 0)} "
        f"kv_bytes_peak={int(enc['kv_bytes_peak'] or 0)}",
    ]
    return enc, lines


args = argparse.ArgumentParser(add_help=False)  # populated in main()


def main():
    global args
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", choices=["A", "B", "both"], default="both")
    p.add_argument("--reuse", choices=["on", "off"], default="on",
                   help="label only; engine is switched via serve.sh REUSE=")
    p.add_argument("--N", default="1,4,8",
                   help="comma list of concurrent client workers")
    p.add_argument("--K", type=int, default=16, help="requests per point")
    p.add_argument("--prefix-tokens", type=int, default=4000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--url", default="http://127.0.0.1:8081")
    p.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    p.add_argument("--out-jsonl", default=None,
                   help="per-request JSONL (default results/requests_<suite>_<reuse>.jsonl)")
    args = p.parse_args()

    tok = make_tokenizer(args.model_dir)
    rng = random.Random(args.seed)

    # GPU proof: one non-streaming probe; response carries system_fingerprint
    # (mlx-lm builds it from mx.device_info()['architecture']).
    gpu = "unknown"
    try:
        req = urllib.request.Request(
            args.url.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "default_model",
                    "messages": [{"role": "user", "content": "say ok"}],
                    "max_tokens": 4,
                    "stream": False,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            obj = json.loads(r.read().decode())
        gpu = (obj.get("system_fingerprint") or "unknown").split("-")[-1]
        print(f"[bench] gpu={gpu} (system_fingerprint={obj.get('system_fingerprint')})",
              file=sys.stderr)
    except Exception as e:
        print(f"[bench] WARNING: gpu probe failed: {e}", file=sys.stderr)

    ns = [int(x) for x in args.N.split(",")]
    suites = (["A", "B"] if args.suite == "both" else [args.suite])

    for suite in suites:
        base = args.out_jsonl
        for n in ns:
            # Suite A deliberately shares one prefix+tails across all N
            # points (agentic-style reuse). Suite B models a random
            # workload, where prompts never repeat: draw FRESH prompts per
            # concurrency point so the prefix cache cannot warm across N.
            rng = random.Random(args.seed + (1000 if suite == "A" else 2000)
                                + (0 if suite == "A" else 7919 * n))
            prompts = (
                build_suite_a(rng, tok, args.prefix_tokens)
                if suite == "A"
                else build_suite_b(rng, tok, args.K)
            )
            out = (
                base.replace(".jsonl", "")
                + f"_{suite}_{args.reuse}_N{n}.jsonl"
                if base
                else f"results/requests_{suite}_{args.reuse}_N{n}.jsonl"
            )
            print(f"[bench] running suite={suite} N={n} reuse={args.reuse} ...",
                  file=sys.stderr)
            enc, lines = run_point(suite, n, args.reuse, prompts, args.url,
                                   open(out, "w"), gpu)
            for line in lines:
                print(line)
            print(f"[bench] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
