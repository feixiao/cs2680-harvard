#!/usr/bin/env bash
# Mads-Serve (CS2680 A4): OpenAI-compatible serving engine on Apple Silicon.
#
# Engine: mlx-lm HTTP server (mlx_lm.server) with the Mads-Serve metrics
# patch (patches/mlx-lm-metrics.diff) that adds a Prometheus /metrics
# endpoint: prompt-cache (KV prefix-reuse) state, in-flight/queued request
# counts, and prefill/decode token-time counters.
#
# The mlx-lm server's scheduling knobs, mapped onto the serving concepts the
# course measures:
#
#   PROMPT_CACHE_SIZE     KV-cache PREFIX REUSE. Maximum number of distinct
#     KV caches held in an in-memory LRU+trie prompt cache. Each finished
#     segment/request KV is inserted; a new request whose prompt shares a
#     prefix fetches that KV and only prefills the unmatched tail.
#     reuse=on  -> 64  (holds every distinct prefix of a 16-request suite)
#     reuse=off -> 0   (cache trims itself empty; every prompt fully prefills)
#   PROMPT_CACHE_BYTES    byte cap on the prompt cache (default: unbounded,
#     LRU by entry count).
#   DECODE_CONCURRENCY    continuous-batching decode size: up to this many
#     requests decode in one batch (default 32).
#   PROMPT_CONCURRENCY    how many prompts prefill in parallel (default 8).
#   PREFILL_STEP_SIZE     CHUNKED PREFILL: prefill is split into chunks of
#     this many tokens per step (default 2048), so long prefills interleave
#     with decode instead of blocking it.
#   KV_BITS               KV quantization (4/8 bits). Cuts KV memory for long
#     context, BUT mlx-lm disables batching when set, so requests are served
#     one at a time. Kept off (full precision) in the baseline.
#   MAX_TOKENS / TEMP     per-request defaults (server-wide fallbacks).
#   CTX_SIZE              NOTE: the mlx server has no context-size flag. The
#     context is bounded by the model's max_position_embeddings (32768 for
#     Qwen2.5-1.5B) and memory; PROMPT_CACHE_BYTES is the practical cap.
#     There is also no --no-warmup flag: the model is loaded at server
#     start and WARMUP=1 issues a throwaway request to compile Metal kernels.
#
# Usage:
#   ./serve.sh                          # defaults (Qwen2.5-1.5B, reuse on, 8081)
#   REUSE=off ./serve.sh                # disable KV prefix reuse
#   MODEL=... PORT=9091 PROMPT_CACHE_SIZE=32 ./serve.sh
#
# Logs go to logs/serve.log (stdout+stderr), pid to logs/serve.pid.
set -euo pipefail

A4_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$A4_DIR"

# --stop: kill the engine this script started (never touches foreign pids).
for a in "$@"; do
  if [ "$a" = "--stop" ]; then
    if [ -f logs/serve.pid ] && kill -0 "$(cat logs/serve.pid 2>/dev/null)" 2>/dev/null; then
      if ps -p "$(cat logs/serve.pid)" -o command= | grep -q "mlx_lm.server"; then
        kill "$(cat logs/serve.pid)"
        echo "[serve] engine stopped"
      fi
    fi
    exit 0
  fi
done

# --- overridable flag set (env) --------------------------------------------
MODEL="${MODEL:-/Users/Shared/LLM_Models/mlx-community/Qwen2.5-1.5B-Instruct-4bit}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8081}"

# KV prefix reuse: 64 entries holds all 16 shared prefixes of the bench
# (each entry ~= 60 MB for a 4k-token prefix of the 1.5B model).
REUSE="${REUSE:-on}"
if [ "$REUSE" = "on" ]; then
  PROMPT_CACHE_SIZE="${PROMPT_CACHE_SIZE:-64}"
else
  PROMPT_CACHE_SIZE="${PROMPT_CACHE_SIZE:-0}"
fi
PROMPT_CACHE_BYTES="${PROMPT_CACHE_BYTES:-}"     # e.g. 4g; empty = unbounded
DECODE_CONCURRENCY="${DECODE_CONCURRENCY:-32}"
PROMPT_CONCURRENCY="${PROMPT_CONCURRENCY:-8}"
PREFILL_STEP_SIZE="${PREFILL_STEP_SIZE:-2048}"   # chunked prefill chunk size
KV_BITS="${KV_BITS:-}"                           # empty = full-precision KV
KV_GROUP_SIZE="${KV_GROUP_SIZE:-64}"
MAX_TOKENS="${MAX_TOKENS:-512}"
TEMP="${TEMP:-0.0}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
WARMUP="${WARMUP:-1}"                            # 0 = skip throwaway warmup request

VENV_PY="$A4_DIR/.venv/bin/python"

# Offline: the model dir ships its tokenizer; never hit the network.
export HUGGINGFACE_HUB_OFFLINE=1
export HF_HUB_OFFLINE=1
# Make a4_serve importable by the engine (kv_cache.py prefix-cache module).
export PYTHONPATH="${A4_DIR}:${PYTHONPATH:-}"

# Apply the metrics patch (idempotent; re-applies if the venv was reinstalled).
SERVER_PY="$A4_DIR/.venv/lib/python3.14/site-packages/mlx_lm/server.py"
if [ -f "$SERVER_PY" ] && ! grep -q "MLX-MADS METRICS PATCH" "$SERVER_PY"; then
  echo "[serve] applying metrics patch..."
  (cd "$A4_DIR/.venv/lib/python3.14/site-packages" && patch -p1 < "$A4_DIR/patches/mlx-lm-metrics.diff")
fi
if [ ! -f "$SERVER_PY" ]; then
  echo "[serve] ERROR: venv missing at $A4_DIR/.venv" >&2
  exit 1
fi

# Free the port if a stale instance of OUR engine is there (never touch
# anything that is not our engine: only kill if the pidfile matches and the
# process is mlx_lm.server).
if [ -f logs/serve.pid ]; then
  OLD_PID="$(cat logs/serve.pid 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    if ps -p "$OLD_PID" -o command= | grep -q "mlx_lm.server"; then
      echo "[serve] stopping previous engine (pid $OLD_PID)"
      kill "$OLD_PID" || true
      for _ in $(seq 1 20); do
        kill -0 "$OLD_PID" 2>/dev/null || break
        sleep 0.5
      done
    fi
  fi
fi
mkdir -p logs

ARGS=(
  "$VENV_PY" -m mlx_lm.server
  --model "$MODEL"
  --host "$HOST"
  --port "$PORT"
  --decode-concurrency "$DECODE_CONCURRENCY"
  --prompt-concurrency "$PROMPT_CONCURRENCY"
  --prefill-step-size "$PREFILL_STEP_SIZE"
  --max-tokens "$MAX_TOKENS"
  --temp "$TEMP"
  --log-level "$LOG_LEVEL"
)
# KV prefix-cache A/B knob. This mlx-lm version has NO boolean --prompt-cache
# flag; prefix caching is ON by default. --prompt-cache-size 0 evicts every
# entry at insertion (fetch can never hit) => reuse OFF; a real size/byte
# budget => reuse ON.
if [ "${REUSE}" = "on" ]; then
  ARGS+=(--prompt-cache-size "$PROMPT_CACHE_SIZE")
  [ -n "$PROMPT_CACHE_BYTES" ] && ARGS+=(--prompt-cache-bytes "$PROMPT_CACHE_BYTES")
else
  ARGS+=(--prompt-cache-size 0)
fi
[ -n "$KV_BITS" ] && ARGS+=(--kv-bits "$KV_BITS" --kv-group-size "$KV_GROUP_SIZE")

echo "[serve] model=$MODEL port=$PORT reuse=$REUSE (prompt-cache-size=$PROMPT_CACHE_SIZE) decode=$DECODE_CONCURRENCY prompt-cc=$PROMPT_CONCURRENCY prefill-step=$PREFILL_STEP_SIZE"
nohup "${ARGS[@]}" > logs/serve.log 2>&1 &
PID=$!
echo "$PID" > logs/serve.pid

# Wait for the HTTP endpoint (model load + Metal JIT happen before first use).
for _ in $(seq 1 120); do
  if curl -sf "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "[serve] engine exited early; see logs/serve.log" >&2
    tail -20 logs/serve.log >&2 || true
    exit 1
  fi
  sleep 1
done
if ! curl -sf "http://$HOST:$PORT/health" >/dev/null 2>&1; then
  echo "[serve] server did not become healthy; see logs/serve.log" >&2
  exit 1
fi
echo "[serve] engine healthy on http://$HOST:$PORT (pid $PID)"

# Metal kernel warmup: one tiny request so the first real request is not
# paying JIT compile cost (the --no-warmup equivalent for mlx-lm).
if [ "$WARMUP" = "1" ]; then
  curl -s "http://$HOST:$PORT/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"default_model","messages":[{"role":"user","content":"hi"}],"max_tokens":2,"stream":false}' \
    > logs/warmup.json || true
  echo "[serve] warmup done"
fi
exit 0
