#!/usr/bin/env bash
# Один запуск: API (:8000) и веб (:3000, а если занят — следующий свободный).
# Ctrl+C останавливает оба.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVER_PORT="${SERVER_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

port_busy() { lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

if port_busy "$SERVER_PORT"; then
  echo "Порт API $SERVER_PORT занят — освободи его или задай SERVER_PORT=..." >&2
  exit 1
fi
while port_busy "$WEB_PORT"; do
  echo "Порт $WEB_PORT занят другим процессом, беру $((WEB_PORT + 1))" >&2
  WEB_PORT=$((WEB_PORT + 1))
done
echo "Открой http://localhost:$WEB_PORT"

uv run --package preza-server uvicorn server.main:app --port "$SERVER_PORT" &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

pnpm --filter web dev --port "$WEB_PORT"
