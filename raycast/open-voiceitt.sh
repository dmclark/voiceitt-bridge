#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Open Voiceitt Scratchpad
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🪟
# @raycast.description Start Voiceitt Bridge and open the scratchpad in Chrome. Raises the existing window if already open. Required because Voiceitt only attaches to http:// origins.

set -e

# Raycast can launch with a sparse PATH; include the usual Homebrew
# locations so `uv` is found on both Apple Silicon and Intel Macs.
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Resolve this script's real directory (follows symlinks) so we can find
# the repo root regardless of where Raycast symlinked the script from.
# Matches the realpath pattern the send-to-*.sh scripts use.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Daily scratchpad use runs on the FastAPI app.
UV_BIN="$(command -v uv || true)"

# Runtime config dir holds the env file (GOOGLE_API_KEY) and the
# rolling server log. Same layout as the prototype so existing users
# don't need to move their env file.
PAD_DIR="${VOICEITT_BRIDGE_CONFIG:-$HOME/.config/voiceitt-bridge}"
PAD_PORT="${VOICEITT_API_PORT:-7532}"
PAD_TITLE="Voiceitt Scratchpad"
LOG_FILE="$PAD_DIR/server.log"
ENV_FILE="$PAD_DIR/env"
mkdir -p "$PAD_DIR"

# Optional AI mode pre-selection: VOICEITT_AI_MODE=0 (raw) or 1 (AI cleanup).
# Honored by web/script.js via ?ai=0|1 on load. The toggle persists to
# localStorage; this URL override is used by future "dictate-raw" /
# "dictate-ai" Raycast wrappers so the user can pick mode without
# touching the in-page checkbox.
PAD_QUERY=""
case "${VOICEITT_AI_MODE:-}" in
  0) PAD_QUERY="?ai=0" ;;
  1) PAD_QUERY="?ai=1" ;;
esac
PAD_URL="http://localhost:${PAD_PORT}/index.html${PAD_QUERY}"

# Source $PAD_DIR/env so GOOGLE_API_KEY reaches the app. File-sourcing is
# more reliable than Raycast inheriting the user's shell rc on early-boot
# launches. The provider also falls back
# to this file, but sourcing keeps logs and child processes consistent.
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

# 1) If a Chrome window with our title is already open, bring it
#    forward. If a mode was specified ($PAD_QUERY non-empty), also
#    navigate the active tab so the in-page ?ai=0|1 handler picks
#    up the change without the user closing and reopening.
ALREADY_OPEN=$(osascript <<EOF
tell application "Google Chrome"
  set found to false
  repeat with w in windows
    if title of w contains "$PAD_TITLE" then
      set index of w to 1
      activate
      if "$PAD_QUERY" is not "" then
        set URL of active tab of w to "$PAD_URL"
      end if
      set found to true
      exit repeat
    end if
  end repeat
  return found
end tell
EOF
)

if [ "$ALREADY_OPEN" = "true" ]; then
  exit 0
fi

# 2) Make sure the app is running on $PAD_PORT.
if ! lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  if [ -z "$UV_BIN" ]; then
    osascript -e 'display notification "uv not found on PATH; install uv or add it to Raycast PATH." with title "Open Voiceitt Scratchpad"'
    exit 1
  fi

  (
    cd "$REPO_DIR"
    nohup env VOICEITT_BRIDGE_PORT="$PAD_PORT" \
      "$UV_BIN" run uvicorn --app-dir src voiceitt_bridge.app:app \
        --host 127.0.0.1 \
        --port "$PAD_PORT" \
      >>"$LOG_FILE" 2>&1 </dev/null &
    disown 2>/dev/null || true
  )

  # Wait briefly for it to bind.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done

  if ! lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    osascript -e "display notification \"server failed to bind on port $PAD_PORT; check $LOG_FILE\" with title \"Open Voiceitt Scratchpad\""
    exit 1
  fi
else
  # Port already in use. Probe the health endpoint so we do not
  # accidentally open a prototype server or an unrelated local service.
  if ! curl -s -f -o /dev/null "http://localhost:$PAD_PORT/api/health"; then
    osascript -e "display notification \"port $PAD_PORT is busy but not serving Voiceitt Bridge. Set VOICEITT_API_PORT to a free port or stop the other service.\" with title \"Open Voiceitt Scratchpad\""
    exit 1
  fi
fi

# 3) Open the page in a new Chrome window so Voiceitt can attach to it.
open -na "Google Chrome" --args --new-window "$PAD_URL"
