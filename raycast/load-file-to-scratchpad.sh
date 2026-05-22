#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Load File into Scratchpad
# @raycast.mode silent
# @raycast.packageName Voiceitt
# @raycast.icon 📂
# @raycast.description Pop a macOS open-panel; load the chosen file's contents into the Voiceitt Scratchpad's input pane so you can edit by voice and send to your target app.

set -e

PAD_URL="http://localhost:7531"
PAD_TITLE="Voiceitt Scratchpad"

# 1) macOS open-panel via AppleScript. POSIX path so curl gets a sane string.
#    "User cancelled" is osascript error -128; swallow it and exit 0 so
#    Raycast doesn't surface a failure for an intentional cancel.
PICK=$(osascript <<'EOF' 2>/dev/null
try
  set f to choose file with prompt "Load into Voiceitt Scratchpad" without invisibles
  POSIX path of f
on error number -128
  return ""
end try
EOF
)

if [ -z "$PICK" ]; then
  exit 0
fi

# 2) JSON-escape the path. Only `\` and `"` matter for typical macOS paths;
#    keep this dependency-free (no jq) since the rest of the toolkit is bash + curl.
ESC=$(printf '%s' "$PICK" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')

# 3) POST to the bridge. Capture body + status separately so we can show the
#    server's one-line error (e.g. "file too large", "not valid UTF-8") in the
#    failure notification instead of a bare HTTP code.
TMP_BODY=$(mktemp)
trap 'rm -f "$TMP_BODY"' EXIT
HTTP=$(curl -sS -o "$TMP_BODY" -w '%{http_code}' \
  -X POST "$PAD_URL/load" \
  -H 'content-type: application/json' \
  --data "{\"path\":\"$ESC\"}" 2>/dev/null || echo "000")

if [ "$HTTP" != "200" ]; then
  REASON=$(head -c 200 "$TMP_BODY" 2>/dev/null | tr '\n' ' ')
  if [ "$HTTP" = "000" ]; then
    REASON="server not reachable on $PAD_URL — open the Scratchpad first"
  fi
  # AppleScript display-notification: escape embedded double quotes.
  REASON_ESC=$(printf '%s' "$REASON" | sed -e 's/"/\\"/g')
  osascript -e "display notification \"$REASON_ESC\" with title \"Load File into Scratchpad\""
  exit 1
fi

# 4) Bring the Scratchpad window to the front if it's open. The page's
#    EventSource('/events') will pick up the reload event and swap content
#    live; if the page isn't open yet, the next time it loads it will
#    GET /file and pick up what we just stored.
osascript <<EOF >/dev/null 2>&1 || true
tell application "Google Chrome"
  repeat with w in windows
    if title of w contains "$PAD_TITLE" then
      set index of w to 1
      activate
      exit repeat
    end if
  end repeat
end tell
EOF
