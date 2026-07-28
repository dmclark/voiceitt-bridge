#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Send to VS Code
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🟦
# @raycast.description Send the scratchpad's outgoing text to VS Code. Reads /api/scratchpad-state instead of scraping the focused textarea, then synthetic Cmd+V into VS Code. Sticky-Keys safe via cliclick. Does NOT press Return.

set -e
CLICLICK="/opt/homebrew/bin/cliclick"
TARGET_BUNDLE_ID="com.microsoft.VSCode"

# Resolve this script's real directory (follows symlinks) so we can find
# the repo root regardless of where Raycast symlinked the script from.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
API_BASE="${VOICEITT_API_BASE:-http://127.0.0.1:${VOICEITT_API_PORT:-7532}/api}"

# 1) Read the page-owned outgoing buffer from the API. This replaces
#    the old focus-dependent Cmd+A/Cmd+C source scrape, so Raycast sends
#    the final/output text the scratchpad chose rather than whichever
#    textarea happened to be focused when the hotkey fired.
set +e
TO_PASTE=$(VOICEITT_API_BASE="$API_BASE" python3 <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

api_base = os.environ["VOICEITT_API_BASE"].rstrip("/")
try:
    with urllib.request.urlopen(f"{api_base}/scratchpad-state", timeout=0.75) as response:
        state = json.loads(response.read().decode("utf-8"))
except (OSError, urllib.error.URLError, json.JSONDecodeError):
    sys.exit(1)

text = state.get("outgoing_text") or ""
if not text:
    sys.exit(2)
sys.stdout.write(text)
PY
)
STATE_EXIT=$?
set -e

if [ "$STATE_EXIT" -ne 0 ]; then
  osascript -e "display notification \"No outgoing scratchpad text found at $API_BASE. Open the scratchpad and dictate or edit text first.\" with title \"Send to VS Code\""
  exit 1
fi

# 2) Save the user's current text clipboard, then stamp with a sentinel
#    before writing the outgoing text. This does not make clipboard
#    managers forget the transient paste text, but it restores the active
#    clipboard after the send. If the outgoing pbcopy fails, `set -e`
#    exits here with the sentinel on the clipboard instead of letting the
#    later Cmd+V paste stale user content.
ORIGINAL_CLIPBOARD=$(pbpaste || true)
SENTINEL="__voiceitt_copy_sentinel_$RANDOM__"
printf '%s' "$SENTINEL" | pbcopy
printf '%s' "$TO_PASTE" | pbcopy

# 3) Activate the target app and paste into whatever control currently has
#    focus there. No AppleScript "tell app to paste" — most apps have no
#    useful scripting dictionary for editor/text-field paste, so we drive
#    it with a synthetic Cmd+V via cliclick. Keep the post-activate
#    modifier release and w:60 waits exactly as the Sticky-Keys-safe
#    paste ritual requires.
osascript -e "tell application id \"$TARGET_BUNDLE_ID\" to activate"
sleep 0.15
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05
"$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd

# 4) Restore the user's text clipboard after the target app has received
#    Cmd+V. Keep this after the exact paste ritual; restoring earlier can
#    race the target and paste the wrong content.
sleep 0.1
printf '%s' "$ORIGINAL_CLIPBOARD" | pbcopy || true
