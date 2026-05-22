#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Send to iTerm
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🎙️
# @raycast.description Cleanup at send: copy from focused app (Voiceitt textarea), run through voiceitt-transform (fail-open to raw), then paste into the current iTerm tab. Sticky-Keys safe via cliclick. Does NOT press Return.

set -e
CLICLICK="/opt/homebrew/bin/cliclick"

# Resolve this script's real directory (follows symlinks) so we can find
# voiceitt-transform next to it regardless of where Raycast symlinked
# the script from.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
TRANSFORM="$SCRIPT_DIR/voiceitt-transform"

# Source $VOICEITT_BRIDGE_DIR/env so voiceitt-transform sees GOOGLE_API_KEY
# even if Raycast didn't inherit it from the user's shell (lesson 16).
ENV_FILE="${VOICEITT_BRIDGE_DIR:-$HOME/.config/voiceitt-bridge}/env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
LOG_FILE="${VOICEITT_BRIDGE_DIR:-$HOME/.config/voiceitt-bridge}/server.log"

# 1) Stamp clipboard with a sentinel so we can detect whether copy actually fired.
SENTINEL="__voiceitt_copy_sentinel_$RANDOM__"
printf '%s' "$SENTINEL" | pbcopy

# 2) Release any stuck modifiers (Sticky Keys can latch Cmd from earlier typing).
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05

# 3) Sticky-Keys-proof Cmd+A then Cmd+C in the currently focused app.
"$CLICLICK" kd:cmd w:60 t:a w:120 t:c w:60 ku:cmd

# 4) Wait (up to ~1s) for the clipboard to change off the sentinel.
CURRENT=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  CURRENT=$(pbpaste)
  if [ "$CURRENT" != "$SENTINEL" ] && [ -n "$CURRENT" ]; then
    break
  fi
  sleep 0.1
done

# 5) Bail out loudly if copy never landed, instead of pasting stale text.
if [ "$CURRENT" = "$SENTINEL" ] || [ -z "$CURRENT" ]; then
  osascript -e 'display notification "Cmd+A/Cmd+C did not capture text. Make sure the Voiceitt textarea is focused." with title "Send to iTerm"'
  exit 1
fi

# 6) Cleanup at send: run dictated text through voiceitt-transform. FAIL
#    OPEN to raw on any non-zero exit or empty output (non-negotiable 4).
#    Stderr appended to server.log so failures stay debuggable.
set +e
CLEANED=$(printf '%s' "$CURRENT" | "$TRANSFORM" 2>>"$LOG_FILE")
TRANSFORM_EXIT=$?
set -e
if [ "$TRANSFORM_EXIT" -ne 0 ] || [ -z "$CLEANED" ]; then
  TO_PASTE="$CURRENT"
else
  TO_PASTE="$CLEANED"
fi

# 7) Put the text we're actually going to paste onto the clipboard. This
#    is the existing Phase 0 clipboard-ritual paste path; the next commit
#    swaps iTerm specifically over to `tell ... write text ... newline NO`
#    which sidesteps the clipboard entirely.
printf '%s' "$TO_PASTE" | pbcopy

# 8) Activate iTerm so the paste lands in the right app and the right tab.
osascript <<'EOF'
tell application "iTerm"
  activate
  tell current window
    tell current session to select
  end tell
end tell
EOF

# 9) Give iTerm a beat to take focus, then release modifiers again
#    (activation can race with Sticky Keys re-latching Cmd).
sleep 0.15
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05

# 10) Sticky-Keys-proof Cmd+V. Bracketed paste (default in modern iTerm +
#     shells/REPLs incl. Amp CLI) keeps embedded newlines as literal text
#     instead of executing each line.
"$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd
