#!/bin/bash
#
# dev-services.sh — restart the local scratchpad web sidecar and API.
#
# Usage:
#   scripts/dev-services.sh              # restart static web + API
#   scripts/dev-services.sh restart      # restart static web + API
#   scripts/dev-services.sh start        # start any missing service
#   scripts/dev-services.sh stop         # stop both services
#   scripts/dev-services.sh status       # show listeners and URLs
#   scripts/dev-services.sh logs         # print log-tail commands
#
# This script owns the local development server lifecycle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

CONFIG_DIR="${VOICEITT_BRIDGE_CONFIG:-$HOME/.config/voiceitt-bridge}"
ENV_FILE="$CONFIG_DIR/env"

WEB_HOST="${VOICEITT_BRIDGE_HOST:-127.0.0.1}"
WEB_PORT="${VOICEITT_BRIDGE_PORT:-7531}"
WEB_LOG="${VOICEITT_BRIDGE_LOG:-$CONFIG_DIR/server.log}"

API_HOST="${VOICEITT_API_HOST:-127.0.0.1}"
API_PORT="${VOICEITT_API_PORT:-7532}"
API_URL="http://localhost:$API_PORT"
API_BASE_URL="${VOICEITT_API_BASE_URL:-$API_URL/api}"
WEB_URL="http://localhost:$WEB_PORT/index.html?api=$API_BASE_URL"
API_LOG="${VOICEITT_API_LOG:-$CONFIG_DIR/api.log}"

mkdir -p "$CONFIG_DIR"

usage() {
  sed -n '2,/^$/p' "$0" | sed -e 's/^# *//' -e 's/^#$//'
}

die() {
  echo "dev-services: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

source_env() {
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi
}

pids_on_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

stop_port() {
  local label="$1"
  local port="$2"
  local pids
  pids="$(pids_on_port "$port")"
  if [ -z "$pids" ]; then
    echo "$label not running on :$port"
    return
  fi

  echo "Stopping $label on :$port (pids: $pids)"
  kill $pids 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    if [ -z "$(pids_on_port "$port")" ]; then
      return
    fi
    sleep 0.2
  done

  pids="$(pids_on_port "$port")"
  if [ -n "$pids" ]; then
    echo "Force-stopping $label on :$port (pids: $pids)"
    kill -9 $pids 2>/dev/null || true
  fi
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local log_file="$3"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return
    fi
    sleep 0.3
  done

  echo "$label did not become ready at $url; last log lines:" >&2
  tail -40 "$log_file" >&2 || true
  exit 1
}

start_static_web() {
  if [ -n "$(pids_on_port "$WEB_PORT")" ]; then
    echo "Static scratchpad already running: $WEB_URL"
    return
  fi

  [ -f "$REPO_DIR/web/index.html" ] || die "missing web/index.html"
  : >"$WEB_LOG"
  echo "Starting static scratchpad: $WEB_URL"
  nohup python3 -m http.server "$WEB_PORT" \
    --bind "$WEB_HOST" \
    --directory "$REPO_DIR/web" \
    >>"$WEB_LOG" 2>&1 </dev/null &
  disown 2>/dev/null || true
  wait_for_url "Static scratchpad" "$WEB_URL" "$WEB_LOG"
}

start_web() {
  start_static_web
}

start_api() {
  if [ -n "$(pids_on_port "$API_PORT")" ]; then
    echo "API already running: $API_URL"
    return
  fi

  source_env
  : >"$API_LOG"
  echo "Starting API: $API_URL"
  (
    cd "$REPO_DIR"
    VOICEITT_BRIDGE_PORT="$WEB_PORT" \
    uv run uvicorn --app-dir src voiceitt_bridge.app:app \
      --host "$API_HOST" \
      --port "$API_PORT"
  ) >"$API_LOG" 2>&1 &
  disown 2>/dev/null || true
  wait_for_url "API" "$API_URL/api/health" "$API_LOG"
}

print_status() {
  echo "scratchpad web (static): $WEB_URL"
  local web_pids
  web_pids="$(pids_on_port "$WEB_PORT")"
  if [ -n "$web_pids" ]; then
    echo "  running on :$WEB_PORT (pids: $web_pids)"
  else
    echo "  stopped"
  fi

  echo "API: $API_URL"
  echo "  browser API base: $API_BASE_URL"
  local api_pids
  api_pids="$(pids_on_port "$API_PORT")"
  if [ -n "$api_pids" ]; then
    echo "  running on :$API_PORT (pids: $api_pids)"
  else
    echo "  stopped"
  fi
}

print_logs() {
  echo "scratchpad web log:"
  echo "  tail -f '$WEB_LOG'"
  echo "API log:"
  echo "  tail -f '$API_LOG'"
}

require_command lsof
require_command curl
require_command python3
require_command uv

case "${1:-restart}" in
  start)
    start_web
    start_api
    print_status
    print_logs
    ;;
  stop)
    stop_port "API" "$API_PORT"
    stop_port "scratchpad web" "$WEB_PORT"
    ;;
  restart)
    stop_port "API" "$API_PORT"
    stop_port "scratchpad web" "$WEB_PORT"
    start_web
    start_api
    print_status
    print_logs
    ;;
  status)
    print_status
    print_logs
    ;;
  logs)
    print_logs
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
