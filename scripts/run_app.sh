#!/usr/bin/env zsh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "Backend venv missing. Running setup-backend..."
  make -C "$ROOT_DIR" setup-backend
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend node_modules missing. Running setup-frontend..."
  make -C "$ROOT_DIR" setup-frontend
fi

echo "Starting TalentMetrics..."
echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
echo "Press CTRL+C to stop both."

cleanup() {
  echo "
Stopping TalentMetrics..."
  if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "$FRONTEND_PID" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}

trap cleanup INT TERM EXIT

cd "$BACKEND_DIR"
.venv/bin/uvicorn app.main:app --port 8000 &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
