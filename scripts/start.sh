#!/bin/bash
# Start both backend and frontend servers for FIRE dashboard.
# Usage: ./scripts/start.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV="$HOME/.local/bin/uv"

cd "$PROJECT_DIR"

# Kill any stale processes on our ports
echo "Cleaning up stale processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true
sleep 1

# Start backend
echo "Starting backend on :8000..."
$UV run uvicorn api.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend (load nvm so npm is available)
echo "Starting frontend on :5173..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
cd "$PROJECT_DIR/dashboard"
npm run dev &
FRONTEND_PID=$!

cd "$PROJECT_DIR"

# Wait for backend to be ready
echo "Waiting for backend..."
for i in $(seq 1 15); do
  if curl -s --max-time 2 http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
  sleep 1
done

echo ""
echo "FIRE is running:"
echo "  Dashboard: http://localhost:5173"
echo "  API:       http://localhost:8000/api/health"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for either to exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
