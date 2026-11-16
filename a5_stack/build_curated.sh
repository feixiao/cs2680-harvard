#!/bin/bash
# Pre-build the curated small terminal-bench task images with the exact names
# trial_handler computes at run time (tb__<task-id>__client), so a later
# `tb run ... --no-rebuild` starts instantly.
set -euo pipefail
cd "$(dirname "$0")/terminal-bench-core/tasks"

TASKS=(hello-world count-dataset-tokens grid-pattern-transform \
       organization-json-generator fix-permissions)

for t in "${TASKS[@]}"; do
  prefix="tb__${t}"
  echo "==> building ${prefix}__client"
  ( cd "$t" \
    && T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME="${prefix}__client" \
       T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME="${prefix}__client" \
       T_BENCH_TASK_DOCKER_NAME_PREFIX="${prefix}" \
       T_BENCH_TEST_DIR=/tests \
       T_BENCH_TASK_LOGS_PATH=/logs \
       T_BENCH_CONTAINER_LOGS_PATH=/logs \
       docker compose -f docker-compose.yaml build --quiet )
done
echo "done"
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep '^tb__' || true
