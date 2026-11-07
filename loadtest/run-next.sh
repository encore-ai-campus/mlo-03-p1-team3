#!/usr/bin/env bash
# Repeat the verified health workload at 100 -> 200 -> 400 concurrent users.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$project_root/.venv/bin/python" "$project_root/loadtest/run.py" \
  --host http://192.168.219.191 --profile health \
  --stages 100,200,400 --warmup 10 --seconds 60 --cooldown 10 \
  --max-fail-ratio 0.01 --max-p95-ms 500 \
  --prometheus-url http://192.168.219.198:9090 \
  --loki-url http://192.168.219.199:3100 "$@"
