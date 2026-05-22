#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Send to VS Code
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🟦
# @raycast.description Cleanup at send: copy from focused app (Voiceitt textarea), run through voiceitt-transform (fail-open to raw), then synthetic Cmd+V into VS Code. Sticky-Keys safe via cliclick. Does NOT press Return.

set -e
CLICLICK="/opt/homebrew/bin/cliclick"
TARGET_BUNDLE_ID="com.microsoft.VSCode"

# Resolve this script's real directory (follows symlinks) so we can find
# voiceitt-transform next to it regardless of where Raycast symlinked
# the script from. Matches the realpath pattern voiceitt-transform itself
# uses to find prompts/default.md.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
TRANSFORM="$SCRIPT_DIR/voiceitt-transform"

# Source $VOICEITT_BRIDGE_DIR/env so voiceitt-transform sees GOOGLE_API_KEY
# even if Raycast didn't inherit it from the user's shell (lesson 16).
# Defaults to ~/.config/voiceitt-bridge, matching open-voiceitt.sh.
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
  osascript -e 'display notification "Cmd+A/Cmd+C did not capture text. Make sure the Voiceitt textarea is focused." with title "Send to VS Code"'
  exit 1
fi

# 6) Cleanup at send: run dictated text through voiceitt-transform. FAIL
#    OPEN to raw on any non-zero exit or empty output (non-negotiable 4) —
#    the user is mid-dictation; never leave them with an empty paste and
#    a cryptic error. Append transform stderr to the same server.log the
#    prototype uses so failures stay debuggable. `set +e` is required so
#    we can inspect TRANSFORM_EXIT instead of aborting on non-zero.
set +e
CLEANED=$(printf '%s' "$CURRENT" | "$TRANSFORM" 2>>"$LOG_FILE")
TRANSFORM_EXIT=$?
set -e
if [ "$TRANSFORM_EXIT" -ne 0 ] || [ -z "$CLEANED" ]; then
  TO_PASTE="$CURRENT"
else
  TO_PASTE="$CLEANED"
fi

# 7) Put the text we're actually going to paste onto the clipboard.
printf '%s' "$TO_PASTE" | pbcopy

# 8) Activate the target app and paste into whatever control currently has
#    focus there. No AppleScript "tell app to paste" — most apps have no
#    useful scripting dictionary for editor/text-field paste, so we drive
#    it with a synthetic Cmd+V via cliclick (same Sticky-Keys-safe ritual
#    as steps 2-3). This is the generic cliclick-paste strategy used by
#    every non-iTerm send-to-*.sh.
osascript -e "tell application id \"$TARGET_BUNDLE_ID\" to activate"
sleep 0.15
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05
"$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd
