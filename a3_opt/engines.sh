#!/usr/bin/env bash
# Start/stop the two mlx-lm engines A3 routing needs (1.5B starter @8082,
# 35B-A3B standard @8083). Reuses a4_serve's venv. The expert tier
# (qwen3.8-27b-splash @1234, LM Studio) is always up.
#
#   opt/engines.sh start | stop | status
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
A4VENV="$HERE/../a4_serve/.venv"
MODELS=/Users/Shared/LLM_Models
PY="$A4VENV/bin/python"
[ -x "$PY" ] || { echo "a4_serve venv missing — wait for A4 phase" >&2; exit 1; }

start_one() { # port model path
  local port=$1 model=$2
  if curl -sf -m 2 "http://localhost:$port/v1/models" >/dev/null; then
    echo "engine already up on :$port"
    return
  fi
  echo "starting $model on :$port (first load takes 1-3 min)..."
  nohup "$A4VENV/bin/mlx_lm" server --model "$model" --port "$port" \
      --prompt-cache-bytes 8589934592 \
      --prompt-concurrency 1 --decode-concurrency 1 \
      > "/tmp/mlx-$port.log" 2>&1 &
  echo $! > "/tmp/mlx-$port.pid"
  for i in $(seq 1 60); do
    sleep 5
    curl -sf -m 2 "http://localhost:$port/v1/models" >/dev/null && { echo "up: :$port"; return; }
  done
  echo "engine on :$port did not come up; log:"; tail -20 "/tmp/mlx-$port.log"; exit 1
}

case "${1:-status}" in
  start)
    # 8084 (35B standard) and 1234 (27B expert, LM Studio) are managed
    # elsewhere; this script only starts the 1.5B starter tier.
    start_one 8082 "$MODELS/mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    ;;
  stop)
    [ -f "/tmp/mlx-8082.pid" ] && kill "$(cat /tmp/mlx-8082.pid)" 2>/dev/null && rm -f "/tmp/mlx-8082.pid"
    ;;
  status)
    for p in 8082 8084 1234; do
      curl -sf -m 2 "http://localhost:$p/v1/models" >/dev/null && echo "up: :$p" || echo "down: :$p"
    done
    ;;
esac
