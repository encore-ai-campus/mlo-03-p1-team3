#!/bin/bash
# cron passes an explicit Node executable: no interactive shell or nvm setup required.
set -euo pipefail
cd "$(dirname "$0")/.."
node_bin="${1:?Usage: run-scheduled.sh /absolute/path/to/node [--prepare-only]}"
shift
exec "$node_bin" personas/scripts/run-scheduled.mjs "$@"
