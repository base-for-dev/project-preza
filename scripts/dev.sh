#!/usr/bin/env bash
# Один запуск: API (:8000) и веб (:3000). Ctrl+C останавливает оба.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --package server uvicorn server.main:app --port "${SERVER_PORT:-8000}" &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

pnpm --filter web dev
