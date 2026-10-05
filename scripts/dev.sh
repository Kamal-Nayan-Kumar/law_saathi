#!/usr/bin/env bash
# Start the API and web dev servers together, for local work.
#
#   ./scripts/dev.sh            # API on :8000, web on :3000
#   ./scripts/dev.sh --observe  # also writes the agent observability log
#
# The observability log is off by default: it appends one JSON line per
# question. Turning it on costs nothing but a file, and
# `python3 api/scripts/agent_stats.py` reads it back.
set -uo pipefail
cd "$(dirname "$0")/.."

OBS=""
for arg in "$@"; do
  case "$arg" in
    --observe) OBS="LAWSAATHI_OBS_LOG=$PWD/tmp/agent-runs.jsonl" ;;
  esac
done
mkdir -p tmp

# SQLite for local work: WAL is set by app/db.py, so overlapping requests work.
export DATABASE_URL="${DATABASE_URL:-sqlite:///./tmp/dev.db}"

pkill -f "uvicorn app.main" 2>/dev/null
pkill -f "next dev" 2>/dev/null
sleep 1

echo "API  -> http://localhost:8000"
echo "WEB  -> http://localhost:3000"
[ -n "$OBS" ] && echo "OBS  -> tmp/agent-runs.jsonl (api/scripts/agent_stats.py)"
echo

# shellcheck disable=SC2086
env $OBS .venv/bin/uvicorn app.main:app --app-dir api --port 8000 --reload &
API_PID=$!

(cd web && npm run dev) &
WEB_PID=$!

trap 'kill $API_PID $WEB_PID 2>/dev/null' INT TERM
wait