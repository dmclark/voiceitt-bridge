# Voiceitt-bridge

> **Status** This repo is the next-gen successor to the [voiceitt-amp-bridge](https://github.com/dmclark/voiceitt-amp-bridge) prototype.It's very much a work in progress, with no clear vision of who this initial README is for.
>
> **MVP** stands for "Minimum Viable Product"

A sm all toolkit that lets you:
- dictate text with [Voiceitt](https://www.voiceitt.com/) (a Chrome-only voice dictation extension for users with atypical speech)
- optionally clean it up with an LLM (grammar, punctuation etc)
- send the result straight into **whatever Mac app you're working in** — a terminal, an editor (`VS Code`), a chat tool (`Slack`, `Discord`, `Messages`) -- anything that accepts a `Cmd+V` paste — via Raycast hotkeys.

## Why

Voiceitt only works in Chrome. Most writing happens outside the browser. [Raycast 2](https://www.raycast.com/) does have dictation capabilities but does not support atypical speech. By combining the two, you can dictate text with Voiceitt and then clean it up with an LLM and send it to any Mac app you're working in.

> **Status** This repo is the next-gen successor to the [voiceitt-amp-bridge](https://github.com/dmclark/voiceitt-amp-bridge) prototype.

---

## 🚀 Quick Start (For New Users)

**Note** These steps are also available as an automated script in `scripts/install.sh` — see the script for details.
Follow these steps to get up and running quickly:

1. **Install prerequisites** (if you don't already have them):
   ```bash

   # Install Homebrew if you don't have it
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
   # Install required tools
   brew install cliclick jq
   
   # Verify Python 3 is available
   python3 --version
   ```

2. **Get a Google Gemini API key**:
   - Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - Create a free API key

3. **Set up your API key** (recommended method):
   ```bash
   mkdir -p ~/.config/voiceitt-bridge
   echo 'GOOGLE_API_KEY=your_key_here' >> ~/.config/voiceitt-bridge/env
   chmod 600 ~/.config/voiceitt-bridge/env
   ```

4. **Install Voiceitt**:
   - Install [Google Chrome](https://www.google.com/chrome/) if you don't have it
   - Sign up for a [Voiceitt Account](https://web.voiceitt.com/sign-up) (free 30-day trial)
   - Install the [Voiceitt Chrome extension](https://chromewebstore.google.com/) (search "Voiceitt")

5. **Install Raycast**:
   - Download and install [Raycast](https://www.raycast.com)

6. **Set up the Raycast scripts**:
   ```bash
   mkdir -p ~/.config/raycast/scripts
   for s in open-voiceitt.sh load-file-to-scratchpad.sh send-to-iterm.sh send-to-vscode.sh; do
     ln -sf "$PWD/raycast/$s" ~/.config/raycast/scripts/"$s"
   done
   ```

7. **Grant necessary permissions**:
   - **Accessibility**: System Settings → Privacy & Security → Accessibility → Add Raycast
   - **Automation**: When you first use each send-to-* script, macOS will prompt you to grant automation permission to Raycast for the target app

8. **Launch the scratchpad**:
   - Open Raycast and search for "Open Voiceitt Scratchpad"
   - This will start the local server and open Chrome to the interface

9. **Start dictating**:
   - Click the microphone icon in the Voiceitt extension
   - Dictate your text
   - Use your Raycast hotkeys to send the cleaned text to your desired application

---

## 📋 What This Repo Contains

```
voiceitt-bridge/
├── README.md         ← you are here
├── HANDOFF.md        ← spec, non-negotiables, lessons pointers, open decisions
├── AGENTS.md         ← root routing doc for AI assistants
├── prompts/          ← LLM system prompts (cleanup, …)
├── web/              ← scratchpad page (vanilla HTML/CSS/JS, no build step)
├── bridge/           ← HTTP server (serve.py) — serves web/, owns the four endpoints
├── raycast/          ← Raycast Script Commands + the cleanup transform
├── notes/            ← parking lot, design notes (empty in MVP)
├── scripts/          ← dev convenience (toggle, install)
└── salvage/          ← verbatim artifacts from the prototype; reference only
```

**Note**: The `src/voiceitt_bridge/` directory (FastAPI app, prompt loader, framing module, pluggable providers) is the planned post-MVP re-architecture. MVP keeps `bridge/serve.py` as the server (Voiceitt won't attach to `file://` URLs, so a local HTTP server is required) — but MVP Python is free to take `uv`-managed dependencies, add a `pyproject.toml`, and span multiple files as needed. What's deferred is the FastAPI package rewrite, not Python itself.

---

## 🔧 How It Works
Each `send-to-*` Raycast hotkey follows this flow:

1. Voiceitt dictation goes to clipboard (with sentinel + poll mechanism)
2. `voiceitt-transform` processes the text via Gemini API (bash + curl + jq)
3. Cleaned text is sent to target application:
   - **iTerm**: Uses AppleScript `write text … newline NO` (bypasses clipboard)
   - **Other apps** (VS Code, etc.): Uses clipboard + cliclick Cmd+V (Sticky-Keys-safe ritual)

The in-page AI toggle in `web/script.js` remains off by default (non-negotiable 5); the send-time cleanup above is the canonical MVP cleanup path.

---

## ⚙️ Configuration

### GOOGLE_API_KEY

`voiceitt-transform` requires a Google Gemini API key to clean up dictated text. **It will not run without `GOOGLE_API_KEY` in its environment** — this is the most common MVP setup failure.

**Two ways to provide it** (in order of preference):

1. **`~/.config/voiceitt-bridge/env` file** (recommended):
   ```bash
   mkdir -p ~/.config/voiceitt-bridge
   echo 'GOOGLE_API_KEY=your_actual_key_here' >> ~/.config/voiceitt-bridge/env
   chmod 600 ~/.config/voiceitt-bridge/env
   ```

2. **Shell environment**:
   - If you've already exported `GOOGLE_API_KEY` in `.zshrc` / `.bashrc`, Raycast inherits it on launch
   - Note: The env file is sourced after shell env, so file values win if both are set

If the key is missing, expired, or invalid, `voiceitt-transform` exits non-zero and the `send-to-*` script falls back to pasting the raw transcript (fail-open behavior). There's no user-visible indication of this in MVP — check `~/.config/voiceitt-bridge/server.log` for stderr if pastes look unexpectedly raw.

---

## 📎 Clipboard Hygiene (Important!)

Every `send-to-*` hotkey under the clipboard ritual pollutes clipboard-history tools. To prevent this immediately:

**Raycast → Settings → Extensions → Clipboard History → Excluded Apps → add Raycast.**

This stops Raycast's own clipboard history from logging every dictation transition. The iTerm `write text` strategy in `raycast/send-to-iterm.sh` further reduces pollution by bypassing the clipboard entirely.

---

## ⌨️ Hotkeys (MVP)

| Script | Purpose | Paste Strategy |
|--------|---------|----------------|
| `raycast/open-voiceitt.sh` | Open the scratchpad (raises existing Chrome window if found; else starts `bridge/serve.py` on `:7531` and opens a new window) | — |
| `raycast/load-file-to-scratchpad.sh` | macOS open-panel → `POST /load` into the scratchpad | — |
| `raycast/send-to-iterm.sh` | Cleanup-at-send → iTerm `write text … newline NO` | Bypasses clipboard |
| `raycast/send-to-vscode.sh` | Cleanup-at-send → VS Code via clipboard + cliclick Cmd+V | Clipboard (transient) |

**Other targets** (Slack, Notes, browser textareas) are not yet wired in MVP — add by copying `raycast/send-to-vscode.sh`, changing `TARGET_BUNDLE_ID`, and the `@raycast.title`. Each new target needs its own Automation-permission prompt the first time it fires.

---

## 🚫 What's Not in This MVP

Explicitly out of scope (see [HANDOFF.md](./HANDOFF.md) for full list):
- The FastAPI re-architecture: the FastAPI app and the `src/voiceitt_bridge/` package (MVP may still use `uv`, `pyproject.toml`, and tests — what's deferred is the package rewrite, not Python deps)
- The `clipboard-restore` save-and-restore wrapper around the clipboard ritual (next PR)
- Any Raycast Extension work (post-MVP+)
- Prompt-picker UI (post-MVP+)
- Multi-provider LLM dispatch (post-MVP+; design-time only)

---

## ⚠️ Known Limitations (MVP)

These gaps are intentional for MVP; each is addressed by post-MVP work:
- **No user-visible feedback when cleanup fails** — if `voiceitt-transform` errors, times out, or sees a missing `GOOGLE_API_KEY`, the `send-to-*` script silently falls back to pasting the raw transcript. Check `~/.config/voiceitt-bridge/server.log` for the transform's stderr if a paste looks unexpectedly raw.
- **No way to switch cleanup prompts at runtime** — `prompts/default.md` is always used
- **No in-page preview-and-edit before sending** — the hotkey fires immediately
- **No diff UI showing raw vs. cleaned** — when the LLM rewrites something you meant literally, you must manually re-dictate
- **Clipboard pollution from non-iTerm targets** — mitigated today by adding Raycast to Clipboard History exclusions (see above)

---

## 📚 Reference Material

- [HANDOFF.md](./HANDOFF.md) — the spec, non-negotiables, and the MVP / post-MVP split
- [salvage/README.md](./salvage/README.md) — index of verbatim artifacts carried over from the prototype
- [salvage/notes/LESSONS-LEARNED.md](./salvage/notes/LESSONS-LEARNED.md) — 37 numbered "we already tried that" entries
- [salvage/snippets/cliclick-paste-ritual.md](./salvage/snippets/cliclick-paste-ritual.md) — source of truth for any new `send-to-*` paste step

---

## 🆘 Troubleshooting

**Nothing happens when I use a send-to-* hotkey:**
1. Check if the Voiceitt scratchpad is open and has dictated text
2. Verify `GOOGLE_API_KEY` is set correctly (see Configuration section)
3. Look at `~/.config/voiceitt-bridge/server.log` for error messages
4. Ensure you've granted Automation permissions to Raycast for the target app

**The pasted text looks exactly like my raw dictation (not cleaned):**
This usually means the Gemini API call failed. Check `~/.config/voiceitt-bridge/server.log` for details about the failure.

**Raycast can't find my scripts:**
1. Verify you created the symlinks correctly in `~/.config/raycast/scripts/`
2. Try running `ls -la ~/.config/raycast/scripts/` to see if the symlinks exist and point to the right place