# Voiceitt-bridge

> **Development branch note:** this `v1` branch is the in-progress
> post-MVP re-architecture of `voiceitt-bridge`. The current working
> scratchpad/Raycast workflow is still based on `bridge/serve.py`; new
> FastAPI-backed `/api/*` work is being built alongside it and should
> not be treated as the stable daily-use path yet.

`voiceitt-bridge` lets you dictate with [Voiceitt](https://www.voiceitt.com/)
in Chrome, optionally clean the text with an LLM, and send the result
into local macOS apps via [Raycast](https://www.raycast.com/) hotkeys.

It is the successor to the
[voiceitt-amp-bridge](https://github.com/dmclark/voiceitt-amp-bridge)
prototype. The current project constraints and MVP/post-MVP boundary live
in [`PROJECT-SPEC.md`](./PROJECT-SPEC.md); this README is the user-facing
setup and daily-use guide.

With it, you can:
- dictate text with Voiceitt, a Chrome-only voice dictation extension for users with atypical speech;
- optionally clean it up with an LLM for grammar, punctuation, and light formatting;
- send the result straight into **whatever Mac app you're working in** — a terminal, an editor (`VS Code`), a chat tool (`Slack`, `Discord`, `Messages`), or anything else that accepts a paste — via Raycast hotkeys.

## Why

Voiceitt only works in Chrome. Most writing happens outside the browser.
[Raycast](https://www.raycast.com/) has dictation features, but it does
not support atypical speech. By combining Voiceitt, a local browser
scratchpad, and Raycast Script Commands, you can dictate with Voiceitt
and send the resulting text to the Mac app where you actually need it.

---

## 🚀 Quick Start

The steps below describe the current MVP daily-use workflow. On the
`v1` branch, new architecture work is intentionally being added beside
that workflow rather than replacing it immediately.

These steps are also available as an automated script:

```bash
./scripts/install.sh
# or, to configure cleanup in one step:
./scripts/install.sh YOUR_GOOGLE_API_KEY
```

Manual setup:

1. **Install prerequisites** (if you don't already have them):
   ```bash

   # Install Homebrew if you don't have it
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
   # Install required tools
   brew install cliclick
   
   # Verify Python 3 is available. The current bridge is stdlib-only;
   # bridge/pyproject.toml records the uv-managed Python project metadata.
   python3 --version
   ```

2. **Get a Google Gemini API key**:
   - Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - Create a free API key

3. **Set up your API key** (recommended for LLM cleanup):
   ```bash
   mkdir -p ~/.config/voiceitt-bridge
   echo 'GOOGLE_API_KEY=your_key_here' >> ~/.config/voiceitt-bridge/env
   chmod 600 ~/.config/voiceitt-bridge/env
   ```

   If you skip this, the bridge still works: cleanup fails open and the
   raw dictated transcript is sent instead.

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
   - Use your Raycast hotkeys to send the selected text — cleaned when AI is on, raw when AI is off or cleanup fails — to your desired application

---

## 📋 What This Repo Contains

```
voiceitt-bridge/
├── README.md         ← you are here
├── PROJECT-SPEC.md   ← spec, non-negotiables, lessons pointers, answered decisions
├── AGENTS.md         ← root routing doc for AI assistants
├── prompts/          ← LLM system prompts (cleanup, …)
├── web/              ← scratchpad page (vanilla HTML/CSS/JS, no build step)
├── bridge/           ← HTTP server (serve.py) — serves web/, owns the four endpoints
├── raycast/          ← Raycast Script Commands + the cleanup transform
├── notes/            ← parking lot, todo list, design notes
├── scripts/          ← dev convenience (toggle, install)
└── salvage/          ← verbatim artifacts from the prototype; reference only
```

**Note**: The `src/voiceitt_bridge/` directory (FastAPI app, prompt loader, framing module, pluggable providers) is the planned post-MVP re-architecture. MVP keeps `bridge/serve.py` as the server (Voiceitt won't attach to `file://` URLs, so a local HTTP server is required) — but MVP Python is free to take `uv`-managed dependencies, add a `pyproject.toml`, and span multiple files as needed. What's deferred is the FastAPI package rewrite, not Python itself.

---

## 🔧 How It Works

Each `send-to-*` Raycast hotkey follows this flow:

1. Voiceitt dictation is captured from the scratchpad with the sentinel + poll clipboard ritual.
2. If the scratchpad's AI toggle is on, `bridge/voiceitt-transform.py` processes the text via Gemini API (Python 3 stdlib — `urllib`, no `curl`/`jq`). If the AI toggle is off, the raw transcript is used.
3. The selected text — cleaned when AI is on, raw when AI is off or cleanup fails — is sent to the target application:
   - **iTerm**: Uses AppleScript `write text … newline NO` (bypasses clipboard)
   - **Other apps** (VS Code, etc.): Uses clipboard + cliclick Cmd+V (Sticky-Keys-safe ritual)

The in-page AI toggle in `web/script.js` remains off by default
(non-negotiable 5). The page mirrors that toggle to the local server so
the Raycast send commands know whether to run cleanup-at-send.

---

## ⚙️ Configuration

### GOOGLE_API_KEY

`bridge/voiceitt-transform.py` requires a Google Gemini API key to clean
up dictated text. **It will not run without `GOOGLE_API_KEY` in its
environment** — this is the most common MVP setup failure.

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

If the key is missing, expired, or invalid, `bridge/voiceitt-transform.py`
exits non-zero and the `send-to-*` script falls back to pasting the raw
transcript (fail-open behavior). There's no user-visible indication of
this in MVP — check `~/.config/voiceitt-bridge/server.log` for stderr if
pastes look unexpectedly raw.

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

Explicitly out of scope (see [PROJECT-SPEC.md](./PROJECT-SPEC.md) for full list):
- The FastAPI re-architecture: the FastAPI app and the `src/voiceitt_bridge/` package (MVP may still use `uv`, `pyproject.toml`, and tests — what's deferred is the package rewrite, not Python deps)
- The `clipboard-restore` save-and-restore wrapper around the clipboard ritual (next PR)
- Any Raycast Extension work (post-MVP+)
- Prompt-picker UI (post-MVP+)
- Multi-provider LLM dispatch (post-MVP+; design-time only)

---

## ⚠️ Known Limitations (MVP)

These gaps are intentional for MVP; each is addressed by post-MVP work:
- **No user-visible feedback when cleanup fails** — if `bridge/voiceitt-transform.py` errors, times out, or sees a missing `GOOGLE_API_KEY`, the `send-to-*` script silently falls back to pasting the raw transcript. Check `~/.config/voiceitt-bridge/server.log` for the transform's stderr if a paste looks unexpectedly raw.
- **No way to switch cleanup prompts at runtime** — `prompts/default.md` is always used
- **No in-page preview-and-edit before sending** — the hotkey fires immediately
- **No diff UI showing raw vs. cleaned** — when the LLM rewrites something you meant literally, you must manually re-dictate
- **Clipboard pollution from non-iTerm targets** — mitigated today by adding Raycast to Clipboard History exclusions (see above)

---

## 📚 Reference Material

- [PROJECT-SPEC.md](./PROJECT-SPEC.md) — current project spec, non-negotiables, answered decisions, and MVP/post-MVP split
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
