#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Open Voiceitt Scratchpad
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🪟
# @raycast.description Start a tiny localhost HTTP server (so Chrome extensions like Voiceitt work) and open the Scratchpad in Chrome.

PAD_DIR="$HOME/.config/voiceitt-bridge"
PAD_PORT=7531
PAD_TITLE="Voiceitt Scratchpad"
LOG_FILE="$PAD_DIR/server.log"
ENV_FILE="$PAD_DIR/env"

# Optional AI mode pre-selection: VOICEITT_AI_MODE=0 (raw) or 1 (AI cleanup).
# Honored by dictate.html via ?ai=0|1 — overrides the in-page localStorage
# toggle on load. Used by the dictate.sh / dictate-ai.sh wrappers so the
# user can pick raw vs LLM-cleanup as separate Raycast commands without
# flipping the in-page checkbox first. Unset = honor existing toggle.
PAD_QUERY=""
case "${VOICEITT_AI_MODE:-}" in
  0) PAD_QUERY="?ai=0" ;;
  1) PAD_QUERY="?ai=1" ;;
esac
PAD_URL="http://localhost:${PAD_PORT}/dictate.html${PAD_QUERY}"

# Source $PAD_DIR/env if it exists, so server.py + voiceitt-transform see
# secrets like $GOOGLE_API_KEY even when Raycast didn't inherit them from
# the user's shell. Plain `KEY=value` lines (no `export` needed); see
# ROADMAP §1 open question #3 / ERD §1.5.
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

# 1) If a Chrome window with our title is already open, just bring it forward.
#    If a mode was specified ($PAD_QUERY non-empty), also navigate the active
#    tab to the new URL so the in-page ?ai=0|1 handler picks up the change
#    without forcing the user to close and reopen. Title-match guarantees
#    the active tab IS the scratchpad (Chrome window title == active tab title).
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

# 2) Make sure our local HTTP server is running on $PAD_PORT.
#    Uses bridge/serve.py (a small http.server subclass) so the page can
#    POST /transform to invoke voiceitt-transform server-side. See
#    ERD §1.4 / §1.6 and bridge/serve.py for why we don't use plain
#    `python3 -m http.server` anymore.
if ! lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  # Start in the background, detached, surviving this script's exit.
  nohup env VOICEITT_BRIDGE_PORT="$PAD_PORT" VOICEITT_BRIDGE_DIR="$PAD_DIR" \
    python3 "$PAD_DIR/serve.py" \
    >>"$LOG_FILE" 2>&1 </dev/null &
  disown 2>/dev/null || true

  # Wait briefly for it to bind.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
fi

# 3) Open the page in a new Chrome window so Voiceitt can attach to it.
open -na "Google Chrome" --args --new-window "$PAD_URL"
