# a4_serve — Mads-Serve: a measurable open-source LLM serving engine (CS2680 A4)

The course assignment targets **SGLang on an RTX-4500 cluster** — unreachable from
this machine. This directory is the local equivalent: an open-source engine
(**mlx-lm** on Apple Metal) whose three serving knobs — continuous batching,
chunked prefill, and KV-cache prefix reuse — we can turn and measure. Same
concepts, same measurements; the course's cluster just lives in a venv here.

## What it is

| Component | What it does |
|---|---|
| `serve.sh` | One-command engine start on port **8081** with a documented, env-overridable flag set; applies the server patch; `--stop` to kill it. |
| `bench_synth.py` | OpenAI-compatible synthetic load client (stdlib). Suite **A** = 16 prompts sharing a ~4k-token prefix + ~100-token tails; suite **B** = random prompt lengths 100–4k, outputs 50–200. Runs N = 1, 4, 8 (sequential / concurrent); records per-request TTFT, TPOT, e2e, tokens, `cached_tokens`; prints `METRIC key=value` lines per point. |
| `metrics.py` | Polls the engine `/metrics` (added by the patch) and summarizes: batch-size distribution, queue depth, KV bytes/peak, cache hit/miss + skipped tokens, prefill vs decode token rates. |
| `kv_cache.py` | The course's finer-grained prefix cache, in production form: content-addressed **16-token blocks** with chained CRC32 hashes, LRU + refcount eviction, `match_prefix` / `register` / `stats`. |
| `patches/mlx-lm-metrics.diff` | The upstream contribution: a 409-line patch to `mlx_lm/server.py` (re-applied automatically by `serve.sh`; survives venv reinstalls). |
| `run_baseline.sh` | Runs the whole matrix: reuse {on,off} × suite {A,B} × N {1,4,8}, with `metrics.py` sampling each leg; writes everything under `results/`. |
| `results/` | Measured baseline (`baseline.md` + machine outputs). |

## The server patch (three contributions)

1. **`/metrics` endpoint** (Prometheus text): prompt-cache entries/bytes by
   type, cache hit/miss/skipped-token counters, in-flight and queued request
   gauges, prompt/decode token and time counters, active-KV and peak memory.
2. **Paged prefix cache mirror**: every request's token prefix is fed to
   `kv_cache.PagedKVCache` (Main's module) and its block-level stats are
   exposed as `mlx_lm_paged_kv_*` — the course's block-paging design running
   live alongside the engine's built-in trie cache.
3. **A real concurrency bug fix** (root cause + defense-in-depth):
   `_generate`'s batch-result dispatch used `del batch_results[uid]` with a
   *stale* `uid` left over from the cache-save loop, so two concurrent
   requests could crash the whole generation thread (`KeyError: <uid>`; every
   later request got `404 generation thread died`). Fixed at the root
   (`del batch_results[r.uid]`) **and** both dispatch loops now use
   `batch_results.get(r.uid)` with a logged skip, so no dispatch path can
   ever kill the thread. Without it, the N=4/8 points of the baseline are
   un-runnable against any stock mlx-lm server.

## The engine and its knobs

Model: `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (reused from disk,
`/Users/Shared/LLM_Models` — 840 MB, loads in seconds). 1.5B chosen over the
brief's 8B preference: HF download is ~3.4 MB/s here (an 8B Q8_0 would take
~45 min), and the 1.5B runs fast enough that all 12 bench points complete in
minutes, including decode-bound concurrency points. Swap with `MODEL=...`.
**GPU proof**: `system_fingerprint` in every response is
`...Mach-O-applegpu_g16s` (`applegpu` = Apple Metal GPU; `mx.get_peak_memory`
in `/metrics` tracks the MLX device allocation).

`serve.sh` flags (env-overridable; each documented in the script):

| Env | Default | mlx-lm flag | Meaning |
|---|---|---|---|
| `REUSE` | `on` | `--prompt-cache-size 64` / `0` | KV prefix reuse A/B. The engine has **no boolean switch** — prefix caching is on by default; size 0 evicts every entry at insertion, so fetch can never hit. |
| `PROMPT_CACHE_SIZE` | 64 / 0 | `--prompt-cache-size` | Max distinct cached KV entries (suite A holds 16 prefixes). |
| `PROMPT_CACHE_BYTES` | (unbounded) | `--prompt-cache-bytes` | Byte budget for cached KV. |
| `DECODE_CONCURRENCY` | 32 | `--decode-concurrency` | Max concurrent decodes (continuous batching width). |
| `PROMPT_CONCURRENCY` | 8 | `--prompt-concurrency` | Prompts prefilled in parallel. |
| `PREFILL_STEP_SIZE` | 2048 | `--prefill-step-size` | Chunked-prefill chunk size (tokens per prefill step). |
| `KV_BITS` / `KV_GROUP_SIZE` | full-precision / 64 | `--kv-bits --kv-group-size` | KV quantization (1.5B fits unquantized; leave off). |
| `MAX_TOKENS`, `TEMP` | 512, 0.0 | `--max-tokens --temp` | Sampling defaults (the bench overrides per request). |
| `WARMUP` | 1 | — | Throwaway request so Metal kernels compile before measurement. |
| `HOST`, `PORT` | 127.0.0.1, 8081 | — | Bind address (LM Studio owns 1234; never touched). |

## Run it

```sh
cd a4_serve
./serve.sh                  # engine on 8081 (reuse on); ./serve.sh --stop
.venv/bin/python bench_synth.py --suite A --reuse on --N 1,4,8
.venv/bin/python bench_synth.py --suite B --reuse off --N 4
.venv/bin/python metrics.py --duration 60 --out results/m.json --label demo
./run_baseline.sh           # full matrix -> results/
```

## Results (measured 2026-11-16, this machine)

See `results/baseline.md` for the full tables; headline numbers:

- **KV prefix reuse is a 9–35× TTFT win on a shared-prefix workload**
  (suite A, 16 reqs sharing a 4.06k prefix): TTFT p50 reuse off → on =
  1570 → 172 ms @ N=1 (9.1×), 3173 → 266 ms @ N=4 (11.9×),
  10777 → 312 ms @ N=8 (34.5×). The off N=8 TTFT is pure prefill queueing.
- **On a random workload reuse buys ~5%** (suite B, N=1: 885 vs 834 ms —
  only the chat-template header matches) — the benefit is concentrated in
  shared prefixes, the agentic pattern.
- **Decode is compute-bound, stops scaling at N≈4**: aggregate generation
  48 → 90 → 116 tok/s for N = 1 → 4 → 8 (suite A); per-token TPOT
  17.8 → 37.8 → 60.2 ms.
- **Memory is the reuse budget**: 16 × 4k-token entries ≈ 5.7 GB of prompt
  cache (process peak 18 GB) vs 3.8 GB with reuse off.

## Design decisions / caveats

- **mlx-lm over llama.cpp**: brew's llama.cpp install stalled for 45+ min
  without a working binary; mlx-lm's venv installed in seconds and its
  `LRUPromptCache` (trie + LRU + byte budget) is exactly the course's
  prefix-reuse mechanism — *and* it reports `usage.prompt_tokens_details.cached_tokens`
  per request, which is the cleanest client-side reuse evidence.
- **Reuse-off via size 0**: evicts on insert; verified `cached_tokens=0` for
  every request and all engine misses in the off legs.
- The `paged_kv_*` metrics are a *shadow mirror* (token ids only) — they report
  what the course's block design *would* skip; they do not alter engine
  behaviour. TTFT conclusions use the engine's own cache (`cached_tokens`).
- The mlx server has no context-size flag; context is bounded by the model
  config (32768) and RAM.
- Determinism: bench tails are seeded; `temperature` fixed per suite; expect
  small run-to-run drift in decode timing (OS scheduler, other tenants on the
  16-core Mac — LM Studio runs concurrently on this box).
