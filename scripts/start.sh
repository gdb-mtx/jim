#!/bin/bash
# Start both backend and frontend servers for FIRE dashboard.
# Usage: ./scripts/start.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV="$HOME/.local/bin/uv"

cd "$PROJECT_DIR"

# Kill any stale processes on our ports
echo "Cleaning up stale processes..."
lsof -ti:8001 | xargs kill -9 2>/dev/null || true
lsof -ti:5174 | xargs kill -9 2>/dev/null || true
sleep 1

# Rotate previous server log into a per-session archive so each restart
# starts a clean file (no session mixing) but we keep recent history for
# post-mortems. Filenames are stamped at rotation time.
LOG_FILE="$PROJECT_DIR/data/api_server.log"
ARCHIVE_DIR="$PROJECT_DIR/data/api_server_logs"
KEEP_LAST=10
mkdir -p "$ARCHIVE_DIR"
if [ -f "$LOG_FILE" ]; then
  STAMP=$(date +%Y%m%dT%H%M%S)
  mv "$LOG_FILE" "$ARCHIVE_DIR/api_server_$STAMP.log"
  # Prune to KEEP_LAST most recent archives
  ls -t "$ARCHIVE_DIR"/api_server_*.log 2>/dev/null \
    | tail -n +$((KEEP_LAST + 1)) \
    | xargs rm -f 2>/dev/null || true
fi
# One-time migration: fold the legacy .prev rotation into the new archive
if [ -f "$LOG_FILE.prev" ]; then
  mv "$LOG_FILE.prev" "$ARCHIVE_DIR/api_server_legacy_prev.log"
fi

# Start backend under `caffeinate -is`:
#   -i prevents idle sleep, -s prevents sleep on AC, AND the spawned child
#   inherits the power assertion which neutralizes macOS App Nap timer
#   throttling on the uvicorn process. Without this, a backgrounded
#   Terminal lets App Nap delay APScheduler timers past their misfire grace.
echo "Starting backend on :8001 (logging to $LOG_FILE)..."
# --timeout-graceful-shutdown: without it a --reload waits forever on any
# in-flight request whose worker thread is stuck, and the server wedges
# with :8001 still listening (2026-08-11 and 2026-09-09 incidents).
caffeinate -is $UV run uvicorn api.main:app --reload --port 8001 \
  --timeout-graceful-shutdown 10 \
  --log-config "$PROJECT_DIR/scripts/log_config.json" \
  >> "$LOG_FILE" 2>&1 &
BACKEND_PID=$!

# Ensure cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

# Wait for backend to be ready BEFORE starting frontend
echo "Waiting for backend..."
BACKEND_READY=false
for i in $(seq 1 30); do
  if curl -s --max-time 2 http://localhost:8001/api/health > /dev/null 2>&1; then
    echo "Backend ready."
    BACKEND_READY=true
    break
  fi
  # Check backend process is still alive
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "ERROR: Backend process exited unexpectedly."
    exit 1
  fi
  sleep 1
done

if [ "$BACKEND_READY" = false ]; then
  echo "ERROR: Backend did not become ready within 30 seconds."
  kill $BACKEND_PID 2>/dev/null
  exit 1
fi

# Start frontend only after backend is confirmed ready
echo "Starting frontend on :5174..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
cd "$PROJECT_DIR/dashboard"
npm run dev &
FRONTEND_PID=$!

cd "$PROJECT_DIR"

echo ""
echo "FIRE is running:"
echo "  Dashboard: http://localhost:5174"
echo "  API:       http://localhost:8001/api/health"
echo "  API Docs:  http://localhost:8001/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for either to exit
wait
