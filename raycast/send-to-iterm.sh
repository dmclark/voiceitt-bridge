#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Send to iTerm
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 🎙️
# @raycast.description Cleanup at send: copy from focused app (Voiceitt textarea). When the page's AI toggle is ON (GET /ai-state == "1"), run through voiceitt-transform (fail-open to raw). When OFF, paste raw — no invisible LLM call. Then write into the current iTerm tab via AppleScript `write text ... newline NO` — bypasses the clipboard and keystroke synthesis on the paste step. Does NOT press Return.

set -e
CLICLICK="/opt/homebrew/bin/cliclick"

# Resolve this script's real directory (follows symlinks) so we can find
# the repo root regardless of where Raycast symlinked the script from.
# voiceitt-transform.py lives in bridge/ (the repo's Python home), one
# level up from this raycast/ script.
SCRIPT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_REAL")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TRANSFORM="$REPO_DIR/bridge/voiceitt-transform.py"

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

# 6) Gate cleanup on the page's AI master toggle. The page POSTs its
#    state to /ai-state on load and on every flip; we curl GET it
#    here. If AI is OFF — or if the curl fails for any reason — we
#    paste raw. "Out is not visible → paste raw" is the user's
#    mental model (see thread T-019e6a4b… for the bug this fixes).
#    Default-to-"0"-on-failure is the safe choice: never invisibly
#    process when uncertain.
AI_PORT="${VOICEITT_BRIDGE_PORT:-7531}"
AI_STATE=$(curl -s --max-time 0.5 "http://127.0.0.1:${AI_PORT}/ai-state" 2>/dev/null || echo "0")
if [ "$AI_STATE" != "1" ]; then
  TO_PASTE="$CURRENT"
else
  # AI is ON: run dictated text through voiceitt-transform. FAIL
  # OPEN to raw on any non-zero exit or empty output (non-negotiable
  # 4). Stderr appended to server.log so failures stay debuggable.
  set +e
  CLEANED=$(printf '%s' "$CURRENT" | "$TRANSFORM" 2>>"$LOG_FILE")
  TRANSFORM_EXIT=$?
  set -e
  if [ "$TRANSFORM_EXIT" -ne 0 ] || [ -z "$CLEANED" ]; then
    TO_PASTE="$CURRENT"
  else
    TO_PASTE="$CLEANED"
  fi
fi

# 7) Write the cleaned (or raw, on fail-open) text directly into the
#    current iTerm session via AppleScript. Per PROJECT-SPEC "Clipboard
#    hygiene and paste strategies": `write text ... newline NO` is atomic, fast,
#    supported by iTerm2's published AppleScript dictionary, and sidesteps
#    both the clipboard and any keystroke synthesis on this paste step
#    (so non-negotiables 1, 6-9 don't even come into play here).
#
#    The text is passed via the TO_PASTE env var and read back inside
#    AppleScript with `system attribute "TO_PASTE"`. This avoids every
#    shell-quoting / AppleScript-escaping pitfall for arbitrary text —
#    embedded newlines, double quotes, backslashes, smart quotes, em
#    dashes, code fences, all pass through verbatim.
#
#    `newline NO` is required (lesson 12); `newline YES` mangles embedded
#    newlines. The user can press Return themselves when ready to submit
#    to amp / claude / their shell.
#
#    Note: the clipboard at this point still holds the raw captured text
#    from step 3, not the cleaned text. That is intentional — we never
#    pollute the clipboard with the cleaned output on the iTerm path.
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
