# Voiceitt Bridge

Voiceitt Bridge turns [Voiceitt](https://www.voiceitt.com/) dictation in Chrome into text you can review and send to local macOS apps with [Raycast](https://www.raycast.com/). It is the FastAPI-based successor to the [voiceitt-amp-bridge prototype](https://github.com/dmclark/voiceitt-amp-bridge).

## Features

- A local FastAPI-served Voiceitt scratchpad, with no frontend build step.
- Optional Gemini cleanup that fails open to the raw transcript if the key, network, provider, or server is unavailable.
- Editable raw and cleaned preview panes with visible transform and API status.
- Backend-owned prompt selection plus local create, edit, validate, activate, and archive controls.
- Backend-owned outgoing state, so Raycast sends the intended text regardless of browser focus.
- Deterministic per-target Raycast hotkeys rather than unreliable focus detection.
- Sticky-Keys-safe clipboard save/restore for clipboard targets, and direct iTerm writing that never touches the clipboard.
- Bounded, in-memory, metadata-only transform diagnostics; transcript content is not included.
- AI cleanup off by default and explicitly controlled in the page.
- `uv`-based installation and runtime.

## Requirements

- macOS, Google Chrome, and the Voiceitt Chrome extension/account
- [Raycast](https://www.raycast.com/)
- [Homebrew](https://brew.sh/), `uv`, and Python 3.12 or newer
- `cliclick` for clipboard-based target commands
- Optional: a [Google Gemini API key](https://aistudio.google.com/apikey)

## Quick start

```bash
git clone https://github.com/dmclark/voiceitt-bridge.git
cd voiceitt-bridge
scripts/install.sh
```

The installer installs `cliclick` and `uv` with Homebrew and symlinks the included Raycast Script Commands. You may pass a Gemini key during setup:

```bash
scripts/install.sh YOUR_GOOGLE_API_KEY
```

Then:

1. Install and sign in to [Voiceitt](https://web.voiceitt.com/sign-up) and enable its Chrome extension.
2. In System Settings → Privacy & Security → Accessibility, grant Raycast access.
3. In Raycast, assign hotkeys to **Open Voiceitt Scratchpad** and each desired **Send to …** command.
4. Run **Open Voiceitt Scratchpad**, dictate into the raw pane, review or edit the outgoing text, and use the target hotkey.
5. Accept macOS Automation prompts the first time Raycast controls each target app.

The local app opens at `http://localhost:7532/`; API docs are at `http://localhost:7532/docs`.

## Configuration

Gemini cleanup is optional. The recommended key location is server-side and user-only:

```bash
mkdir -p ~/.config/voiceitt-bridge
printf '%s\n' 'GOOGLE_API_KEY=your_key_here' > ~/.config/voiceitt-bridge/env
chmod 600 ~/.config/voiceitt-bridge/env
```

An exported `GOOGLE_API_KEY` takes precedence. Other runtime settings:

| Variable | Default | Purpose |
|---|---|---|
| `VOICEITT_API_PORT` | `7532` | FastAPI and scratchpad port |
| `VOICEITT_API_BASE` | `http://127.0.0.1:$VOICEITT_API_PORT/api` | API used by send commands |
| `VOICEITT_TRANSFORM_MODEL` | `gemini-3.1-flash-lite` | Gemini model |
| `VOICEITT_BRIDGE_CONFIG` | `~/.config/voiceitt-bridge` | Runtime config directory |
| `VOICEITT_AI_MODE` | unset | Open with AI forced off (`0`) or on (`1`) |

AI is off by default. Its page setting persists in browser storage and can be overridden with `?ai=0` or `?ai=1`.

## Architecture and how it works

1. FastAPI serves `web/` and the local `/api/*` endpoints.
2. The browser mirrors the AI setting, raw text, chosen outgoing text, and outgoing kind to `/api/scratchpad-state`.
3. With AI enabled, `/api/transforms` frames the transcript, uses the backend-selected prompt, and calls Gemini. Any failure returns raw text rather than an empty result.
4. Both text panes remain editable. The browser publishes the current sendable value whenever either pane changes.
5. A target-specific Raycast command reads `outgoing_text` from the API. Clipboard targets activate a fixed bundle ID, paste with modifier-release delays that tolerate Sticky Keys, then restore the previous text clipboard. iTerm receives text through AppleScript `write text ... newline NO` and does not submit it.

Packaged prompts in `prompts/*.md` are defaults. Prompt edits and new prompts are stored locally under ignored `prompts/user/`; archiving moves user files out of the active inventory. Active selection is backend-owned for the current server process.

`GET /api/transforms/recent` exposes a bounded in-process list of status, provider/model, prompt hash, source, duration, and input/output lengths. It contains no raw or cleaned transcript text and is cleared when the server restarts.

## Raycast hotkeys

| Command | Target behavior |
|---|---|
| `open-voiceitt.sh` | Starts the app with `uv` and opens or raises the Chrome scratchpad |
| `send-to-iterm.sh` | Writes outgoing text directly to the current iTerm session; does not press Return |
| `send-to-supacode.sh` | Pastes outgoing text into Supacode and restores the text clipboard |
| `send-to-vscode.sh` | Pastes outgoing text into VS Code and restores the text clipboard |

Assign a distinct Raycast hotkey to each send command. Fixed targets are intentional: Raycast takes focus when invoked, so inferring the previously focused application is not dependable.

### Adding a target command

Find the app bundle ID and generate a command from the existing safe clipboard pattern:

```bash
osascript -e 'id of application "App Name"'
scripts/add-raycast-target.sh \
  --name "App Name" \
  --bundle-id "com.example.App" \
  --icon "📤"
```

Use `--no-install` to create the script without symlinking it, or `--overwrite` to replace an existing generated target. Assign the new command a Raycast hotkey and test it with Sticky Keys enabled.

## Privacy and safety

- The app binds locally; dictated text is sent to Google only when AI is enabled and a Gemini transform runs.
- API keys remain in the server environment or local config file, never browser storage.
- Cleanup is fail-open: raw text remains available when transformation fails.
- Transform diagnostics are metadata-only, bounded, non-durable, and best-effort.
- Clipboard target commands restore the previous text clipboard after pasting. Clipboard-history utilities can still observe the transient outgoing value; consider excluding Raycast from clipboard history. iTerm avoids the clipboard entirely.
- Send commands refuse to paste when backend outgoing state is empty or unavailable, preventing stale clipboard content from being sent.

## Limitations

- Voiceitt requires Chrome and an HTTP-served page; other browsers are not the supported dictation path.
- The service is local and single-user. Scratchpad state, active prompt selection, and diagnostics reset on restart.
- Only Gemini is implemented as a cleanup provider.
- Clipboard restoration preserves text, not arbitrary rich clipboard formats, and clipboard managers may capture transient content.
- macOS Accessibility and per-target Automation permissions require manual approval.
- Send commands insert text but do not press Return or otherwise submit it.

## Development

```bash
uv sync
uv run uvicorn --app-dir src voiceitt_bridge.app:app --host 127.0.0.1 --port 7532
scripts/smoke-test.sh
uv run pytest
```

For side-by-side static-page/API development, `scripts/dev-services.sh` supports `start`, `stop`, `restart`, `status`, and `logs`.

## Troubleshooting

**The scratchpad does not open:** ensure `uv` is installed and port 7532 is free. Check `~/.config/voiceitt-bridge/server.log`.

**A send command reports no outgoing text:** open the scratchpad, enter or dictate text, and confirm the header shows the API as available. The command intentionally will not fall back to focused-window scraping.

**Text stays raw with AI on:** verify the key in `~/.config/voiceitt-bridge/env`, restart the server, and inspect the server log. Provider failures intentionally return raw text.

**Paste does not reach the target:** confirm Raycast has Accessibility access, approve its Automation permission for that app, verify `/opt/homebrew/bin/cliclick` exists, and test the app-specific hotkey again.

**Raycast cannot find commands:** verify the symlinks in `~/.config/raycast/scripts/` or rerun `scripts/install.sh`.

**Clipboard history contains dictation:** restoration cannot prevent clipboard managers observing transient values. Exclude Raycast in Raycast Settings → Extensions → Clipboard History, or use the direct iTerm command.
