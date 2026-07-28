#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Send to iTerm
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🎙️
# @raycast.description Send the scratchpad's outgoing text to iTerm. Reads /api/scratchpad-state instead of scraping the focused textarea, then writes into the current iTerm tab via AppleScript `write text ... newline NO`. Does NOT press Return.

set -e
CLICLICK="/opt/homebrew/bin/cliclick"

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
  osascript -e "display notification \"No outgoing scratchpad text found at $API_BASE. Open the scratchpad and dictate or edit text first.\" with title \"Send to iTerm\""
  exit 1
fi

# 2) Write the outgoing text directly into the current iTerm session via
#    AppleScript. `write text ... newline NO` is atomic, fast,
#    supported by iTerm2's published AppleScript dictionary, and sidesteps
#    both the clipboard and any keystroke synthesis on this paste step
#    and avoids modifier-key accessibility hazards on this paste step.
#
#    The text is passed via the TO_PASTE env var and read back inside
#    AppleScript with `system attribute "TO_PASTE"`. This avoids every
#    shell-quoting / AppleScript-escaping pitfall for arbitrary text —
#    embedded newlines, double quotes, backslashes, smart quotes, em
#    dashes, code fences, all pass through verbatim.
#
#    `newline NO` is required because `newline YES` mangles embedded
#    newlines. The user can press Return themselves when ready to submit
#    to amp / claude / their shell.
#
#    Note: this path does not touch the clipboard at all.
TO_PASTE="$TO_PASTE" osascript <<'EOF'
tell application "iTerm"
  activate
  tell current window
    tell current session
      select
      write text (system attribute "TO_PASTE") newline NO
    end tell
  end tell
end tell
EOF
