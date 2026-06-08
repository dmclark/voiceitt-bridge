# AGENTS.md — `raycast/` conventions

Raycast Script Commands (bash, with `@raycast.*` header metadata).
The cleanup CLI they shell out to — `voiceitt-transform.py` (Python 3
stdlib — `urllib`/`json`, no `curl`/`jq`/pip deps; ported from bash) —
now lives in [`../bridge/`](../bridge) (the repo's Python home), not
here; the `send-to-*.sh` scripts resolve it via the repo root. The
Raycast side stays Script Commands until prompt-picker / preferences
work forces a flip to a Raycast Extension (HANDOFF answered open
decision #2).

> **Required reading before editing anything here:**
> 1. [`../HANDOFF.md`](../HANDOFF.md) non-negotiables 1, 6, 7, 8, 9
>    (input synthesis + clipboard + per-target hotkey rules).
> 2. [`../salvage/snippets/cliclick-paste-ritual.md`](../salvage/snippets/cliclick-paste-ritual.md)
>    — **byte-for-byte source of truth**. Any new `send-to-*` script
>    must match this ritual, including the `w:60` waits and the
>    modifier-release lines.
> 3. [`../salvage/notes/LESSONS-LEARNED.md`](../salvage/notes/LESSONS-LEARNED.md)
>    lessons 6–16 (Sticky Keys, cliclick, permissions, env inheritance).

## Conventions

- **Bash, not zsh.** `#!/bin/bash`, `set -e` at the top.
- **`@raycast.*` header metadata in a comment block** immediately
  after the shebang. Title, mode (`silent` for fire-and-forget),
  packageName (`Voiceitt`), icon, description. Keep descriptions
  honest — they're what the user sees in Raycast's command listing.
- **Numbered comments per step.** `# 1) …`, `# 2) …`. The paste
  ritual is fiddly; the comments are how the next reader (you in
  six months, or another AI) figures out which lines are
  load-bearing.
- **`osascript <<'EOF' ... EOF`** for AppleScript heredocs. Single
  quotes around `EOF` so `$VARS` aren't expanded into the
  AppleScript source.
- **Cliclick path constant at the top:**
  `CLICLICK="/opt/homebrew/bin/cliclick"`. Apple Silicon assumed;
  swap if running on Intel.

## The Sticky-Keys-safe paste ritual (non-negotiable)

Every `send-to-*` script that pastes via the clipboard must use the
exact ritual in
[`../salvage/snippets/cliclick-paste-ritual.md`](../salvage/snippets/cliclick-paste-ritual.md).
In short:

```bash
# 1) Sentinel-stamp the clipboard so we can detect copy actually fired.
SENTINEL="__voiceitt_copy_sentinel_$RANDOM__"
printf '%s' "$SENTINEL" | pbcopy

# 2) Release any latched modifiers (Sticky Keys can leave Cmd held).
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05

# 3) Cmd+A then Cmd+C in the focused app. w:60 / w:120 are required.
"$CLICLICK" kd:cmd w:60 t:a w:120 t:c w:60 ku:cmd

# 4) Poll pbpaste for up to ~1s; bail loudly if sentinel never cleared.

# (After cleanup-via-voiceitt-transform and pbcopy of the cleaned text:)
# 5) Activate target, sleep 0.15, release modifiers again, Cmd+V.
osascript -e "tell application id \"$TARGET_BUNDLE_ID\" to activate"
sleep 0.15
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05
"$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd
```

**Do not "simplify" this.** Each `w:`, each `sleep`, each
modifier-release line is there because the obvious shorter version
fails intermittently under load or under Sticky Keys. See lesson 8.

## The MVP cleanup-at-send flow

```diagram
focused app ──Cmd+A,Cmd+C──▶ clipboard ──pbpaste──▶ voiceitt-transform
                                                        │
                                                        ▼ stdout
                                              pbcopy (cleaned text)
                                                        │
                                                        ▼
                                          target app receives paste
                                          (cliclick Cmd+V, or iTerm
                                           `write text … newline NO`)
```

`voiceitt-transform` is **fail-open** (non-negotiable 4): if it errors
or times out, the wrapping `send-to-*` script falls back to the raw
captured text and pastes that, rather than leaving the user with an
empty output. Verify this explicitly when editing.

## Per-target paste-strategy map

| Bundle id | Target | Strategy | Touches clipboard? |
|---|---|---|---|
| `com.googlecode.iterm2` | iTerm2 | `iterm-write` — `tell application "iTerm2" to tell current session to write text "…" newline NO` | No |
| `com.microsoft.VSCode` | VS Code | `clipboard-restore` (MVP: clipboard ritual; restore wrapper next PR) | Yes (transient) |
| `com.tinyspeck.slackmacgap` | Slack | `clipboard-restore` (not wired in MVP) | Yes (transient) |
| *anything else* | (add per target) | `clipboard-restore` default | Yes (transient) |

When adding a target: copy `send-to-vscode.sh`, change
`TARGET_BUNDLE_ID`, the `@raycast.title`, the `@raycast.icon`, and
the notification copy. **Macros first time:** macOS will surface a
"Allow Raycast to control <App>" permission prompt (lesson 14);
mention this to the user so they don't mistake it for an error.

## What `voiceitt-transform` expects

- `GOOGLE_API_KEY` in env (sourced from
  `$VOICEITT_BRIDGE_DIR/env`, default `~/.config/voiceitt-bridge/env`,
  by `open-voiceitt.sh` — see lesson 16 for why this is in a file
  rather than relying on shell inheritance).
- `python3` on PATH (stdlib only — no `curl`, no `jq`, no pip deps).
- Reads dictated text from stdin, writes cleaned text on stdout.
- Exits non-zero on any error. The wrapping `send-to-*` script must
  catch and fall back to raw text (non-negotiable 4).
- Wraps the input in `<TRANSCRIPT>…</TRANSCRIPT>` before sending to
  Gemini (non-negotiable 3, lesson 17). Do not strip this framing.

## Verification (no automated substitute exists)

1. **Sticky Keys ON.** System Settings → Accessibility → Keyboard
   → Sticky Keys. Every paste-ritual change must be tested with this
   on. Without it, the test proves nothing (lesson 8).
2. **Dictate → cleanup → send-to-*** end-to-end through the actual
   scratchpad page. Confirm:
   - Multi-line output (lists, code fences, em-dashes, smart quotes)
     arrives intact in the target.
   - LLM failure path: kill the network or `GOOGLE_API_KEY` and
     re-fire; the raw transcript should still land in the target
     (fail-open).
   - Stale clipboard path: focus a different app before the hotkey
     fires; the script should bail loudly with a notification, not
     paste stale clipboard contents.
3. **Re-fire the same hotkey twice** rapidly; confirm no Cmd-latch
   leftover wreaks havoc on the next keystroke.

## Things that will look tempting and are forbidden

- ❌ `cliclick t:"..."` (type-instead-of-paste). Per-character
  keystrokes including modifier-bearing chars; Sticky Keys turns
  this into latched-modifier chaos. (HANDOFF "Considered and
  rejected".)
- ❌ `osascript -e '... keystroke "v" using command down'`. Silently
  swallowed under Sticky Keys. (Lesson 6, non-negotiable 1.)
- ❌ `tell application "iTerm" to write text "…" newline yes`.
  Mangles embedded newlines. (Lesson 12.) Use `newline NO` and let
  the user hit Return.
- ❌ Adding `cliclick` to System Settings → Privacy & Security →
  Accessibility. Accessibility is per-controlling-process; grant it
  to the invoking app (Raycast). (Lesson 15.)
- ❌ Hard-coding `GOOGLE_API_KEY` anywhere in this repo. Lives in
  `~/.config/voiceitt-bridge/env` only. (Lesson 18.)
