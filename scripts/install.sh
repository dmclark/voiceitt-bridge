#!/bin/bash
#
# install.sh — automated setup for voiceitt-bridge
#
# This script automates the one-time setup steps described in README.md.
# It makes GOOGLE_API_KEY optional — if not provided, cleanup will fail-open
# to pasting raw transcripts (as per non-negotiable 4).
#
# Usage:
#   ./install.sh [GOOGLE_API_KEY]
#   GOOGLE_API_KEY=your_key ./install.sh
#
# If GOOGLE_API_KEY is omitted, you'll need to set it up manually later
# in ~/.config/voiceitt-bridge/env or your shell environment.

set -euo pipefail

# Configuration
RAYCAST_DIR="$HOME/.config/raycast/scripts"
VOICEITT_CONFIG_DIR="$HOME/.config/voiceitt-bridge"
MVP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/raycast"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Parse arguments
if [ $# -gt 1 ]; then
  log_error "Too many arguments. Usage: $0 [GOOGLE_API_KEY]"
  exit 1
fi

API_KEY_PROVIDED=false
if [ $# -eq 1 ]; then
  if [ -n "$1" ] && [ "$1" != "" ]; then
    GOOGLE_API_KEY="$1"
    API_KEY_PROVIDED=true
  fi
fi

# Also check environment variable
if [ -z "${GOOGLE_API_KEY:-}" ]; then
  GOOGLE_API_KEY="${GOOGLE_API_KEY:-}"
fi

# Step 1: Check prerequisites
log_info "Checking prerequisites..."

# Check if we're on macOS
if [[ "$(uname)" != "Darwin" ]]; then
  log_error "This script is designed for macOS only."
  exit 1
fi

# Check for Homebrew
if ! command -v brew &>/dev/null; then
  log_error "Homebrew not found. Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if ! command -v brew &>/dev/null; then
    log_error "Failed to install Homebrew."
    exit 1
  fi
fi

# Check for Python 3
if ! command -v python3 &>/dev/null; then
  log_error "Python 3 is required but not installed. Please install Python 3 first."
  exit 1
fi

# Step 2: Install required packages
log_info "Installing required packages (cliclick)..."
brew install cliclick

# Step 3: Set up GOOGLE_API_KEY (if provided)
if [ "$API_KEY_PROVIDED" = true ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
  log_info "Setting up GOOGLE_API_KEY..."
  
  # Create config directory if it doesn't exist
  mkdir -p "$VOICEITT_CONFIG_DIR"
  
  # Write API key to env file
  echo "GOOGLE_API_KEY=$GOOGLE_API_KEY" > "$VOICEITT_CONFIG_DIR/env"
  chmod 600 "$VOICEITT_CONFIG_DIR/env"
  
  log_info "API key saved to $VOICEITT_CONFIG_DIR/env"
else
  log_warn "GOOGLE_API_KEY not provided. Skipping API key setup."
  log_warn "Without an API key, voiceitt-transform will fail-open to pasting raw transcripts."
  log_warn "To enable LLM cleanup, set GOOGLE_API_KEY later:"
  log_warn "  echo 'GOOGLE_API_KEY=your_key' >> $VOICEITT_CONFIG_DIR/env"
  log_warn "  chmod 600 $VOICEITT_CONFIG_DIR/env"
fi

# Step 4: Symlink Raycast Script Commands
log_info "Setting up Raycast Script Command symlinks..."
mkdir -p "$RAYCAST_DIR"

# List of scripts to symlink (excluding voiceitt-transform.py as it's resolved via realpath)
SCRIPTS_TO_SYMLINK=(
  open-voiceitt.sh
  load-file-to-scratchpad.sh
  send-to-iterm.sh
  send-to-supacode.sh
  send-to-vscode.sh
)

for script in "${SCRIPTS_TO_SYMLINK[@]}"; do
  source_path="$MVP_DIR/$script"
  target_path="$RAYCAST_DIR/$script"
  
  if [ ! -f "$source_path" ]; then
    log_error "Source script not found: $source_path"
    log_error "Make sure you're running this script from the voiceitt-bridge repository root."
    exit 1
  fi
  
  # Create symlink (overwrite existing)
  ln -sf "$source_path" "$target_path"
  log_info "Symlinked $script"
done

log_info "Raycast scripts symlinked to $RAYCAST_DIR"

# Step 5: Provide next steps
echo
log_info "Setup complete! Next steps:"
echo
echo -e "${YELLOW}1. Grant Accessibility permission to Raycast:${NC}"
echo "   System Settings → Privacy & Security → Accessibility"
echo "   → Add Raycast if not already listed"
echo
echo -e "${YELLOW}2. Grant Automation permission to Raycast (per-app):${NC}"
echo "   The first time you use each send-to-* hotkey, macOS will prompt you"
echo "   to grant automation permission to Raycast for the target app"
echo
echo -e "${YELLOW}3. Launch the Voiceitt scratchpad:${NC}"
echo "   Open Raycast and search for 'Open Voiceitt Scratchpad'"
echo "   (This will start the local server and open Chrome)"
echo
echo -e "${YELLOW}4. Install and configure Voiceitt (if not already done):${NC}"
echo "   - Install Google Chrome (if you don't have it)"
echo "   - Sign up for a Voiceitt account: https://web.voiceitt.com/sign-up"
echo "   - Install the Voiceitt Chrome extension (search 'Voiceitt' in Chrome Web Store)"
echo

if [ "$API_KEY_PROVIDED" = false ] && [ -z "${GOOGLE_API_KEY:-}" ]; then
  echo -e "${YELLOW}⚠️  Important: GOOGLE_API_KEY not configured${NC}"
  echo "   The system will work but will fail-open to pasting raw transcripts"
  echo "   (no LLM cleanup). To enable cleanup:"
  echo "   1. Get a key at https://aistudio.google.com/apikey"
  echo "   2. Run: echo 'GOOGLE_API_KEY=your_key' >> $VOICEITT_CONFIG_DIR/env"
  echo "   3. Run: chmod 600 $VOICEITT_CONFIG_DIR/env"
  echo
fi

echo -e "${GREEN}🎉 Setup finished! Refer to README.md for detailed usage instructions.${NC}"
