#!/bin/bash
#
# add-raycast-target.sh — generate a per-app Raycast send-to-* Script Command.
#
# Each target app needs its own Raycast command because Raycast steals focus
# when invoked; the target cannot be detected reliably at send time.
#
# Usage:
#   scripts/add-raycast-target.sh --name "Supacode" --bundle-id "app.supabit.supacode" [--icon "🟪"] [--no-install]
#
# To discover a bundle id for an installed app:
#   osascript -e 'id of application "Supacode"'

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
RAYCAST_DIR="$REPO_DIR/raycast"
TEMPLATE="$RAYCAST_DIR/send-to-vscode.sh"
RAYCAST_SCRIPT_COMMANDS_DIR="$HOME/.config/raycast/scripts"

APP_NAME=""
BUNDLE_ID=""
ICON="📤"
INSTALL=true
OVERWRITE=false

usage() {
  sed -n '2,/^$/p' "$0" | sed -e 's/^# *//' -e 's/^#$//'
}

die() {
  echo "add-raycast-target: $*" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --name)
      [ $# -ge 2 ] || die "--name requires a value"
      APP_NAME="$2"
      shift 2
      ;;
    --bundle-id)
      [ $# -ge 2 ] || die "--bundle-id requires a value"
      BUNDLE_ID="$2"
      shift 2
      ;;
    --icon)
      [ $# -ge 2 ] || die "--icon requires a value"
      ICON="$2"
      shift 2
      ;;
    --no-install)
      INSTALL=false
      shift
      ;;
    --overwrite)
      OVERWRITE=true
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[ -n "$APP_NAME" ] || die "missing --name"
[ -n "$BUNDLE_ID" ] || die "missing --bundle-id"
[ -f "$TEMPLATE" ] || die "template not found: $TEMPLATE"

SLUG="$(printf '%s' "$APP_NAME" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
[ -n "$SLUG" ] || die "could not derive script name from app name: $APP_NAME"

TARGET_SCRIPT="$RAYCAST_DIR/send-to-$SLUG.sh"
if [ -e "$TARGET_SCRIPT" ] && [ "$OVERWRITE" != true ]; then
  die "$TARGET_SCRIPT already exists; pass --overwrite to replace it"
fi

python3 - "$TEMPLATE" "$TARGET_SCRIPT" "$APP_NAME" "$BUNDLE_ID" "$ICON" <<'PY'
import sys
from pathlib import Path

template_path, target_path, app_name, bundle_id, icon = sys.argv[1:]
text = Path(template_path).read_text()

text = text.replace("# @raycast.title Send to VS Code", f"# @raycast.title Send to {app_name}")
text = text.replace("# @raycast.icon 🟦", f"# @raycast.icon {icon}")
text = text.replace("Then synthetic Cmd+V into VS Code.", f"Then synthetic Cmd+V into {app_name}.")
text = text.replace('TARGET_BUNDLE_ID="com.microsoft.VSCode"', f'TARGET_BUNDLE_ID="{bundle_id}"')
text = text.replace('with title "Send to VS Code"', f'with title "Send to {app_name}"')
text = text.replace("# 8) Activate the target app", "# 8) Activate the target app")

Path(target_path).write_text(text)
PY

chmod +x "$TARGET_SCRIPT"
echo "Created $TARGET_SCRIPT"

if [ "$INSTALL" = true ]; then
  mkdir -p "$RAYCAST_SCRIPT_COMMANDS_DIR"
  ln -sf "$TARGET_SCRIPT" "$RAYCAST_SCRIPT_COMMANDS_DIR/$(basename "$TARGET_SCRIPT")"
  echo "Symlinked to $RAYCAST_SCRIPT_COMMANDS_DIR/$(basename "$TARGET_SCRIPT")"
  echo "Raycast will show it as: Send to $APP_NAME"
fi

cat <<EOF

Next steps:
  1. Assign a hotkey in Raycast for "Send to $APP_NAME".
  2. First run: accept the macOS "Allow Raycast to control $APP_NAME" Automation prompt.
  3. Smoke-test with Sticky Keys ON: dictate → send → confirm paste lands in $APP_NAME.
EOF
