#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Open Voiceitt Scratchpad
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🪟
# @raycast.description Start the in-repo bridge HTTP server (serving web/) and open the Voiceitt Scratchpad in Chrome. Raises the existing window if already open. Required because Voiceitt only attaches to http:// origins.

# Resolve this script's real directory (follows symlinks) so we can find
# bridge/serve.py, web/, and voiceitt-transform next to it regardless of
# where Raycast symlinked the script from. Matches the realpath pattern
# the send-to-*.sh scripts use.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# In-repo runtime paths. The prototype-era version of this script
# referenced $HOME/.config/voiceitt-bridge/serve.py from a symlink
# farm; the MVP carries serve.py forward into bridge/ so the repo is
# standalone.
SERVE_PY="$REPO_DIR/bridge/serve.py"
WEB_DIR="$REPO_DIR/web"
TRANSFORM_CMD="$REPO_DIR/raycast/voiceitt-transform"

# Runtime config dir holds the env file (GOOGLE_API_KEY) and the
# rolling server log. Same layout as the prototype so existing users
# don't need to move their env file.
PAD_DIR="${VOICEITT_BRIDGE_CONFIG:-$HOME/.config/voiceitt-bridge}"
PAD_PORT="${VOICEITT_BRIDGE_PORT:-7531}"
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

# Source $PAD_DIR/env so GOOGLE_API_KEY lands in the bridge server's
# env (and is inherited by voiceitt-transform subprocesses spawned
# from POST /transform). Required even though the MVP cleanup path
# goes through send-to-*.sh — the in-page AI toggle still hits
# POST /transform if the user enables it, and the same env is needed.
# Lesson 16: file-sourcing is more reliable than Raycast inheriting
# the user's shell rc on early-boot launches.
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

# 2) Make sure our bridge HTTP server is running on $PAD_PORT.
#    VOICEITT_BRIDGE_DIR is hinted at web/ so the page is served
#    from the repo (the serve.py default is the prototype-era
#    ~/.config/voiceitt-bridge — fine for "poke by hand", not the
#    MVP path). VOICEITT_TRANSFORM_CMD points at this repo's
#    voiceitt-transform so POST /transform shells out correctly.
if ! lsof -iTCP:"$PAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  if [ ! -f "$SERVE_PY" ]; then
    osascript -e "display notification \"bridge/serve.py not found at $SERVE_PY\" with title \"Open Voiceitt Scratchpad\""
    exit 1
  fi

  nohup env VOICEITT_BRIDGE_PORT="$PAD_PORT" \
            VOICEITT_BRIDGE_DIR="$WEB_DIR" \
            VOICEITT_TRANSFORM_CMD="$TRANSFORM_CMD" \
    python3 "$SERVE_PY" \
    >>"$LOG_FILE" 2>&1 </dev/null &
  disown 2>/dev/null || true

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
  # Port already in use. Probe /index.html — if it doesn't respond,
  # something other than this repo's server is on the port (most
  # likely the prototype's serve.py serving dictate.html out of
  # ~/.config/voiceitt-bridge/). Bail loudly instead of opening
  # Chrome at a URL that will 404.
  if ! curl -s -f -o /dev/null "http://localhost:$PAD_PORT/index.html"; then
    osascript -e "display notification \"port $PAD_PORT is busy but not serving this repo's web/index.html. The prototype's serve.py may still be running — kill it, or set VOICEITT_BRIDGE_PORT to a free port.\" with title \"Open Voiceitt Scratchpad\""
    exit 1
  fi
fi

# 3) Open the page in a new Chrome window so Voiceitt can attach to it.
open -na "Google Chrome" --args --new-window "$PAD_URL"
