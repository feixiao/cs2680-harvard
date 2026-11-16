#!/usr/bin/env bash
# Sequential full A2 runs on the dedicated mlx 35B-A3B engine (port 8084).
# baseline (no faults) then fault-tolerance (20% injected transient faults).
# The 8084 engine is ours (a2 runs); 1234 stays free for the session/agents.
set -uo pipefail
cd "$(dirname "$0")"
MODEL=$(/usr/bin/python3 -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://localhost:8084/v1/models', timeout=5))['data'][0]['id'])")
echo "== model on 8084: $MODEL"
.venv/bin/python run.py --tag baseline --concurrency 1 \
    --model "$MODEL" --base-url http://localhost:8084/v1 \
    --workdir /tmp/mads-a2-runs 2>&1 | grep -E "^(TASK|METRIC|#|Wall)"
echo "== FAULT RUN"
# concurrency 1: the stock mlx-lm server crashes its generation thread under
# >=2 concurrent requests (KeyError in batch dispatch, see a4_serve notes)
.venv/bin/python run.py --tag fault --concurrency 1 --fault-rate 0.2 \
    --model "$MODEL" --base-url http://localhost:8084/v1 \
    --workdir /tmp/mads-a2-runs 2>&1 | grep -E "^(TASK|METRIC|#|Wall)"
