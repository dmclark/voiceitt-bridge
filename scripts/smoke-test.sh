#!/bin/bash
#
# smoke-test.sh — curl-based checks for the local runtime.
#
# Usage:
#   scripts/smoke-test.sh                    # restart the runtime and run all checks
#   scripts/smoke-test.sh transform          # run transform checks only
#   scripts/smoke-test.sh runtime            # verify health, static assets, and state
#   VOICEITT_SMOKE_SHUTDOWN=1 scripts/smoke-test.sh transform
#
# The script owns the runtime process on VOICEITT_API_PORT, default 7532:
# if something is already listening there, it is stopped and replaced
# with `uv run uvicorn --app-dir src voiceitt_bridge.app:app`.
# By default the server is left running for manual follow-up curls; set
# VOICEITT_SMOKE_SHUTDOWN=1 to stop it when the script exits.
#
# Keep these checks narrow: they are a manual-review aid, not a replacement
# for `uv run pytest` or Voiceitt/Raycast end-to-end testing.

set -euo pipefail

HOST="${VOICEITT_API_HOST:-127.0.0.1}"
PORT="${VOICEITT_API_PORT:-7532}"
BASE_URL="http://$HOST:$PORT"
SERVER_LOG="${VOICEITT_API_LOG:-/tmp/voiceitt-smoke-$PORT.log}"
SHUTDOWN_ON_EXIT="${VOICEITT_SMOKE_SHUTDOWN:-0}"

usage() {
  sed -n '2,/^$/p' "$0" | sed -e 's/^# *//' -e 's/^#$//'
}

die() {
  echo "smoke-test: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

stop_server() {
  local pids
  pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "Stopping API on $BASE_URL (pids: $pids)"
    kill $pids 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      if ! lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        return
      fi
      sleep 0.2
    done

    pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "Force-stopping API on $BASE_URL (pids: $pids)"
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

restart_server() {
  local existing_pids
  existing_pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$existing_pids" ]; then
    echo "Restarting API on $BASE_URL (stopping: $existing_pids)"
    kill $existing_pids 2>/dev/null || true
    sleep 0.5
  else
    echo "Starting API on $BASE_URL"
  fi

  : >"$SERVER_LOG"
  uv run uvicorn --app-dir src voiceitt_bridge.app:app \
    --host "$HOST" \
    --port "$PORT" \
    >"$SERVER_LOG" 2>&1 &

  echo "API pid $!; log: $SERVER_LOG"

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then
      return
    fi
    sleep 0.5
  done

  echo "API did not become ready; last log lines:" >&2
  tail -40 "$SERVER_LOG" >&2 || true
  exit 1
}

curl_json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local response

  echo >&2
  echo "==> $method $path" >&2
  echo "request: $method $BASE_URL$path" >&2
  if [ -n "$body" ]; then
    echo "request body:" >&2
    printf '%s\n' "$body" >&2
    response="$(curl -fsS \
      -X "$method" \
      -H 'content-type: application/json' \
      --data "$body" \
      "$BASE_URL$path")"
  else
    echo "request body: <none>" >&2
    response="$(curl -fsS \
      -X "$method" \
      "$BASE_URL$path")"
  fi
  echo "response body:" >&2
  printf '%s\n' "$response" >&2
  echo >&2
  printf '%s' "$response"
}

json_get() {
  python3 -c '
import json
import sys

path = sys.argv[1].split(".")
value = json.load(sys.stdin)
for part in path:
    value = value[int(part)] if isinstance(value, list) else value[part]
print(value)
' "$1"
}

smoke_health_and_prompts() {
  curl_json GET /api/health | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body == {"status": "ok", "service": "voiceitt-bridge"}, body
print("health ok")
'

  curl_json GET /api/prompts | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert isinstance(body, list), body
if body:
    first = body[0]
    assert {"id", "name", "path", "content_hash"} <= set(first), first
    assert "system_text" not in first, first
print(f"prompts ok ({len(body)} found)")
'
}

smoke_prompt_state() {
  local prompt_state
  prompt_state="$(curl_json GET /api/prompt-state)"
  printf '%s' "$prompt_state" | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert {"active_prompt_id", "updated_at", "updated_by"} <= set(body), body
assert body["active_prompt_id"], body
print("prompt-state read ok")
'

  local active_prompt_id
  active_prompt_id="$(printf '%s' "$prompt_state" | json_get active_prompt_id)"
  curl_json PUT /api/prompt-state \
    "{\"active_prompt_id\":\"$active_prompt_id\",\"updated_by\":\"smoke-test\"}" \
    | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body["updated_by"] == "smoke-test", body
print("prompt-state update ok")
'
}

smoke_service_boundaries() {
  echo
  echo "note: transcript framing and prompt loading are service-level checks; run: uv run pytest"
}

smoke_transforms() {
  curl_json POST /api/transforms \
    '{"raw_text":"um make a directory called source","source":"smoke-test","timeout_ms":1000}' \
    | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body["raw_text"] == "um make a directory called source", body
assert body["cleaned_text"], body
assert body["status"] in {"ok", "disabled", "timeout", "provider_error"}, body
assert body["provider_id"] == "gemini", body
assert body["source"] == "smoke-test", body
assert "failure_reason" in body, body
print("transform ok (%s)" % body["status"])
'

  curl_json POST /api/transforms '{"raw_text":""}' | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body["raw_text"] == "", body
assert body["cleaned_text"] == "", body
assert body["status"] == "empty_input", body
print("empty transform ok")
'
}

smoke_runtime() {
  curl_json GET /api/health | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body == {"status": "ok", "service": "voiceitt-bridge"}, body
print("runtime health ok")
'

  curl_json GET /api/scratchpad-state | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body == {
    "ai_enabled": False,
    "raw_text": "",
    "outgoing_text": "",
    "outgoing_kind": "empty",
}, body
print("scratchpad state ok")
'

  curl -fsS "$BASE_URL/" | python3 -c '
import sys
body = sys.stdin.read()
assert "Voiceitt Scratchpad" in body, body[:200]
print("scratchpad root ok")
'

  curl -fsS "$BASE_URL/script.js" | python3 -c '
import sys
body = sys.stdin.read()
assert "initApi" in body, body[:200]
print("scratchpad asset ok")
'
}

require_command curl
require_command python3
require_command lsof
require_command uv

case "${1:-}" in
  -h|--help|help)
    usage
    exit 0
    ;;
esac

if [ "$SHUTDOWN_ON_EXIT" = "1" ]; then
  trap stop_server EXIT
fi

restart_server

case "${1:-}" in
  "")
    smoke_health_and_prompts
    smoke_prompt_state
    smoke_service_boundaries
    smoke_transforms
    smoke_runtime
    TARGET="all"
    ;;
  health) smoke_health_and_prompts ;;
  prompts) smoke_prompt_state ;;
  services) smoke_service_boundaries ;;
  transform) smoke_transforms ;;
  runtime) smoke_runtime ;;
  *)
    die "unknown check '${1:-}'; expected health, prompts, services, transform, runtime, or no argument for all"
    ;;
esac

TARGET="${TARGET:-$1}"

echo
echo "$TARGET smoke checks passed against $BASE_URL"
