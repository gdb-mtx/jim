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

# Start backend
echo "Starting backend on :8001..."
$UV run uvicorn api.main:app --reload --port 8001 &
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
