#!/bin/bash
#
# toggle-raycast-binding.sh — flip the Raycast Script Command symlinks
# for send-to-iterm.sh and send-to-vscode.sh between the prototype
# (~/voiceitt-amp-bridge/scripts/) and this repo's MVP versions
# (~/voiceitt-bridge/raycast/).
#
# Why only those two? They're the only Script Commands whose behavior
# actually differs between the prototype and MVP. open-voiceitt.sh
# and load-file-to-scratchpad.sh are byte-identical between the two
# (this repo's are verbatim copies), so re-symlinking them buys nothing
# and adds failure surface. The toggle deliberately leaves them alone.
#
# Usage:
#
#   scripts/toggle-raycast-binding.sh             # flip to the other side
#   scripts/toggle-raycast-binding.sh mvp      # force MVP
#   scripts/toggle-raycast-binding.sh prototype   # force prototype
#   scripts/toggle-raycast-binding.sh status      # print current binding, exit
#
# After flipping to mvp, remember to uncheck the "AI" toggle in the
# scratchpad page — MVP cleanup happens at send-time, so the in-page
# AI toggle would double-clean and waste an API call per utterance.

set -e

RAYCAST_DIR="$HOME/.config/raycast/scripts"
PROTOTYPE_DIR="$HOME/voiceitt-amp-bridge/scripts"
MVP_DIR="$HOME/voiceitt-bridge/raycast"
SCRATCHPAD_PORT=7531

# The two Script Commands whose behavior differs between prototype and MVP.
SCRIPTS=(send-to-iterm.sh send-to-vscode.sh)

# Detect the current target of a Script Command symlink. Returns one of:
#   "prototype" | "mvp" | "missing" | "unknown:<actual target>"
detect_one() {
  local script="$1"
  local link="$RAYCAST_DIR/$script"

  if [ ! -L "$link" ]; then
    if [ -e "$link" ]; then
      echo "unknown:not-a-symlink"
    else
      echo "missing"
    fi
    return
  fi

  local target
  target="$(readlink "$link")"
  case "$target" in
    "$PROTOTYPE_DIR/$script") echo "prototype" ;;
    "$MVP_DIR/$script")    echo "mvp" ;;
    *)                        echo "unknown:$target" ;;
  esac
}

# Detect the overall current binding from send-to-iterm.sh. Both scripts
# are expected to be in the same state; the apply step normalizes any drift.
current_binding() {
  detect_one send-to-iterm.sh
}

print_status() {
  echo "Raycast Script Command bindings (looked at $RAYCAST_DIR):"
  for s in "${SCRIPTS[@]}"; do
    local state
    state="$(detect_one "$s")"
    case "$state" in
      prototype) printf '  %s -> prototype\n'        "$s" ;;
      mvp)    printf '  %s -> mvp\n'           "$s" ;;
      missing)   printf '  %s -> (no symlink)\n'     "$s" ;;
      unknown:*) printf '  %s -> %s\n'               "$s" "${state#unknown:}" ;;
    esac
  done
}

apply_target() {
  local target="$1"
  local src_dir

  case "$target" in
    mvp)    src_dir="$MVP_DIR" ;;
    prototype) src_dir="$PROTOTYPE_DIR" ;;
    *)
      echo "apply_target: invalid target '$target'" >&2
      return 2
      ;;
  esac

  if [ ! -d "$RAYCAST_DIR" ]; then
    echo "Raycast Script Commands dir not found: $RAYCAST_DIR" >&2
    echo "(Set the directory in Raycast → Extensions → Script Commands first.)" >&2
    return 1
  fi

  # Sanity-check sources exist before touching any symlinks. We want to
  # fail loudly here, not partway through, so the user is never left with
  # a half-flipped pair (one script at prototype, one at MVP).
  for s in "${SCRIPTS[@]}"; do
    if [ ! -f "$src_dir/$s" ]; then
      echo "missing source: $src_dir/$s" >&2
      echo "(target=$target — is the repo present at the expected path?)" >&2
      return 1
    fi
  done

  for s in "${SCRIPTS[@]}"; do
    ln -sf "$src_dir/$s" "$RAYCAST_DIR/$s"
  done
}

# MVP needs http://localhost:7531/dictate.html served by the prototype's
# serve.py. The toggle can't start the server itself (intentional: that
# would be doing things the user didn't ask for), but it can warn loudly
# when flipping to mvp with nothing listening — the symptom otherwise
# is a confusing "send-to-* did nothing" the next time a hotkey fires.
warn_if_server_missing() {
  if command -v lsof >/dev/null 2>&1; then
    if ! lsof -iTCP:"$SCRATCHPAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      echo
      echo "WARNING: nothing is listening on :$SCRATCHPAD_PORT."
      echo "  MVP still relies on the prototype's serve.py for the scratchpad page."
      echo "  Fire 'Open Voiceitt Scratchpad' in Raycast (or run open-voiceitt.sh) to start it."
    fi
  fi
}

# Parse args.
case "${1:-}" in
  status)
    print_status
    exit 0
    ;;
  mvp|prototype)
    TARGET="$1"
    ;;
  "")
    case "$(current_binding)" in
      prototype) TARGET="mvp" ;;
      mvp)    TARGET="prototype" ;;
      missing|unknown:*)
        echo "Current binding is not recognized; pass 'mvp' or 'prototype' explicitly." >&2
        print_status
        exit 1
        ;;
    esac
    ;;
  -h|--help|help)
    sed -n '2,/^$/p' "$0" | sed -e 's/^# *//' -e 's/^#$//'
    exit 0
    ;;
  *)
    echo "usage: $(basename "$0") [mvp|prototype|status]" >&2
    exit 2
    ;;
esac

PREV="$(current_binding)"
apply_target "$TARGET"

echo "Raycast send-to-* bindings now point at: $TARGET (was: $PREV)"
print_status

if [ "$TARGET" = "mvp" ]; then
  echo
  echo "Reminder: in the scratchpad page, UNCHECK the 'AI' toggle in the header."
  echo "  MVP cleanup happens at send-time; the in-page AI toggle would"
  echo "  double-clean and waste a Gemini call per utterance."
  warn_if_server_missing
fi
