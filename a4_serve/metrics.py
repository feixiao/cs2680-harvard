#!/usr/bin/env python3
"""Mads-Serve /metrics scraper + summarizer (CS2680 A4).

Polls the engine's Prometheus /metrics endpoint (added by the Mads-Serve
metrics patch, patches/mlx-lm-metrics.diff) and summarizes the run:

  * prompt-cache (KV prefix reuse): entries, bytes, per-type entries,
    hit/miss totals, tokens skipped via reuse, hit rate
  * batch size distribution: in-flight request count histogram over samples
  * queue depth: max/mean of waiting requests
  * token rates: prompt (prefill) vs generation tokens/sec from engine
    counters; peak KV bytes (prompt cache + active batch KV); peak memory

Optionally merges a bench_synth.py per-request JSONL to add client-side
TTFT/TPOT/e2e percentiles.

Stdlib only.

Usage:
  python3 metrics.py --url http://127.0.0.1:8081 --duration 300 \
      --out results/metrics_A_on.json --label A_on
  python3 metrics.py --url http://127.0.0.1:8081 --stop-file /tmp/stop \
      --out results/metrics_B_off.json --label B_off \
      --client-jsonl results/requests_B_off_N1.jsonl ...
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request


def scrape(url):
    """One scrape of /metrics -> {name: value}."""
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


def pct(v, q):
    v = sorted(v)
    if not v:
        return None
    k = max(0, min(len(v) - 1, int(round((len(v) - 1) * q))))
    return v[k]


def summarize(samples, client_jsonls=()):
    out = {}
    if not samples:
        return out

    names = set()
    for s in samples:
        names.update(s["values"])
    gauges = [
        "mlx_lm_prompt_cache_entries",
        "mlx_lm_prompt_cache_bytes",
        "mlx_lm_inflight_requests",
        "mlx_lm_queued_requests",
        "mlx_lm_kv_active_bytes",
        "mlx_lm_peak_memory_bytes",
        "mlx_lm_paged_kv_blocks",
        "mlx_lm_paged_kv_cached_tokens",
        "mlx_lm_paged_kv_hit_rate",
    ]
    counters = [
        "mlx_lm_prompt_tokens_total",
        "mlx_lm_prompt_time_seconds_total",
        "mlx_lm_generation_tokens_total",
        "mlx_lm_generation_steps_total",
        "mlx_lm_decode_time_seconds_total",
        "mlx_lm_prompt_cache_hits_total",
        "mlx_lm_prompt_cache_misses_total",
        "mlx_lm_prompt_cache_tokens_reused_total",
        "mlx_lm_requests_completed_total",
        "mlx_lm_paged_kv_prefix_hits_total",
        "mlx_lm_paged_kv_prefix_misses_total",
        "mlx_lm_paged_kv_skipped_tokens_total",
        "mlx_lm_paged_kv_prefilled_tokens_total",
    ]
    t0, t1 = samples[0]["t"], samples[-1]["t"]
    window = max(1e-9, t1 - t0)

    for name in gauges:
        vals = [s["values"].get(name) for s in samples]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        out[name] = {
            "min": min(vals),
            "mean": statistics.fmean(vals),
            "p50": pct(vals, 0.5),
            "p95": pct(vals, 0.95),
            "max": max(vals),
            "last": vals[-1],
        }

    first = {n: samples[0]["values"].get(n, 0) for n in counters}
    last = {n: samples[-1]["values"].get(n, 0) for n in counters}
    for name in counters:
        delta = max(0.0, last.get(name, 0) - first.get(name, 0))
        out[name] = {"delta": delta, "rate": delta / window}

    # Derived summary ------------------------------------------------------------
    hits = out.get("mlx_lm_prompt_cache_hits_total", {}).get("delta", 0)
    misses = out.get("mlx_lm_prompt_cache_misses_total", {}).get("delta", 0)
    n_fetch = hits + misses
    prompt_tok = out.get("mlx_lm_prompt_tokens_total", {}).get("delta", 0)
    gen_tok = out.get("mlx_lm_generation_tokens_total", {}).get("delta", 0)
    steps = out.get("mlx_lm_generation_steps_total", {}).get("delta", 0)

    inflight = [
        s["values"].get("mlx_lm_inflight_requests") for s in samples
    ]
    inflight = [int(v) for v in inflight if v is not None]
    hist = {}
    for v in inflight:
        bucket = "0" if v == 0 else "1" if v == 1 else "2" if v == 2 else \
            "3" if v == 3 else "4-8" if v <= 8 else "9-16" if v <= 16 else ">16"
        hist[bucket] = hist.get(bucket, 0) + 1
    if inflight:
        hist = {k: round(100.0 * v / len(inflight), 1) for k, v in hist.items()}

    kv = [
        (s["values"].get("mlx_lm_prompt_cache_bytes", 0)
         + s["values"].get("mlx_lm_kv_active_bytes", 0))
        for s in samples
    ]

    out["summary"] = {
        "window_s": window,
        "n_samples": len(samples),
        "reuse_hit_rate": round(hits / n_fetch, 4) if n_fetch else None,
        "prompt_tokens": int(prompt_tok),
        "prompt_tok_s": round(prompt_tok / window, 2),
        "generation_tokens": int(gen_tok),
        "generation_tok_s": round(gen_tok / window, 2),
        "decode_tok_per_step": round(gen_tok / steps, 3) if steps else None,
        "inflight_hist_pct": hist,
        "inflight_max": max(inflight) if inflight else None,
        "kv_total_bytes_peak": int(max(kv)) if kv else 0,
        "kv_total_bytes_peak_gb": round(max(kv) / 1e9, 3) if kv else 0,
        "paged_skip_tokens": int(
            out.get("mlx_lm_paged_kv_skipped_tokens_total", {}).get("delta", 0)
        ),
        "paged_prefill_tokens": int(
            out.get("mlx_lm_paged_kv_prefilled_tokens_total", {}).get("delta", 0)
        ),
        "paged_hit_rate": (
            round(
                (out.get("mlx_lm_paged_kv_prefix_hits_total", {}).get("delta", 0))
                / max(
                    1,
                    out.get("mlx_lm_paged_kv_prefix_hits_total", {}).get("delta", 0)
                    + out.get("mlx_lm_paged_kv_prefix_misses_total", {}).get(
                        "delta", 0
                    ),
                ),
                4,
            )
            if any(
                s["values"].get("mlx_lm_paged_kv_hit_rate") is not None
                for s in samples
            )
            else None
        ),
        "peak_memory_gb": round(
            max((s["values"].get("mlx_lm_peak_memory_bytes", 0) for s in samples))
            / 1e9,
            3,
        ),
    }

    # Client-side merge ----------------------------------------------------------
    if client_jsonls:
        recs = []
        for path in client_jsonls:
            if not os.path.exists(path):
                continue
            with open(path) as f:
                recs.extend(json.loads(line) for line in f if line.strip())
        if recs:
            ok = [r for r in recs if r.get("error") is None]
            def stats_of(key, unit):
                vals = [r[key] for r in ok if r.get(key) is not None]
                if not vals:
                    return None
                return {
                    "n": len(vals),
                    "mean": round(statistics.fmean(vals), 1),
                    "p50": round(pct(vals, 0.5), 1),
                    "p95": round(pct(vals, 0.95), 1),
                    "max": round(max(vals), 1),
                }
            out["client"] = {
                "n": len(ok),
                "err": len(recs) - len(ok),
                "ttft_ms": stats_of("ttft_ms", "ms"),
                "tpot_ms": stats_of("tpot_ms", "ms"),
                "e2e_ms": stats_of("e2e_ms", "ms"),
            }
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://127.0.0.1:8081")
    p.add_argument("--interval", type=float, default=0.2)
    p.add_argument("--duration", type=float, default=0,
                   help="seconds to sample (0 = until --stop-file appears)")
    p.add_argument("--stop-file", default=None)
    p.add_argument("--out", required=True, help="JSON output: raw series + summary")
    p.add_argument("--label", default="run")
    p.add_argument("--client-jsonl", action="append", default=[],
                    help="bench per-request JSONL to merge (repeatable)")
    a = p.parse_args()

    end = time.monotonic() + a.duration if a.duration else float("inf")
    samples = []
    while time.monotonic() < end:
        if a.stop_file and os.path.exists(a.stop_file):
            break
        try:
            vals = scrape(a.url)
        except (urllib.error.URLError, OSError):
            time.sleep(1.0)
            continue
        vals = {k: v for k, v in vals.items()
                if not k.startswith("mlx_lm_prompt_cache_entries_by_type")}
        samples.append({"t": time.monotonic(), "values": vals})
        time.sleep(a.interval)

    summary = summarize(samples, a.client_jsonl)
    with open(a.out, "w") as f:
        json.dump({"label": a.label, "summary": summary,
                   "samples": samples}, f)

    s = summary.get("summary", {})
    print(f"METRIC metrics label={a.label} window_s={s.get('window_s', 0):.1f} "
          f"n_samples={s.get('n_samples', 0)}")
    print(f"METRIC metrics label={a.label} reuse_hit_rate={s.get('reuse_hit_rate')} "
          f"prompt_tok_s={s.get('prompt_tok_s')} gen_tok_s={s.get('generation_tok_s')}")
    print(f"METRIC metrics label={a.label} prompt_tokens={s.get('prompt_tokens')} "
          f"gen_tokens={s.get('generation_tokens')} "
          f"decode_tok_per_step={s.get('decode_tok_per_step')}")
    hist = s.get("inflight_hist_pct") or {}
    hist_str = " ".join(f"{k}={v}%" for k, v in sorted(hist.items()))
    print(f"METRIC metrics label={a.label} inflight_hist[{hist_str}] "
          f"inflight_max={s.get('inflight_max')} "
          f"queued_max={summary.get('mlx_lm_queued_requests', {}).get('max')}")
    print(f"METRIC metrics label={a.label} kv_peak_gb={s.get('kv_total_bytes_peak_gb')} "
          f"peak_mem_gb={s.get('peak_memory_gb')} "
          f"cache_bytes_max_gb={summary.get('mlx_lm_prompt_cache_bytes', {}).get('max', 0) / 1e9:.3f}")
    c = summary.get("client")
    if c:
        for k in ("ttft_ms", "tpot_ms", "e2e_ms"):
            st = c.get(k) or {}
            print(f"METRIC metrics label={a.label} client {k} "
                  f"p50={st.get('p50')} p95={st.get('p95')} max={st.get('max')}")
    print(f"[metrics] wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
