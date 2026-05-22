# The Sticky-Keys-safe paste ritual

This is the single most irreplaceable piece of code in the prototype.
Without these exact incantations, dictation under macOS Sticky Keys
silently fails: paste doesn't fire, or Cmd stays latched and the next
keypress triggers a menu shortcut.

If you are rewriting `send-to-*` commands (whether as bash, as a
Raycast Extension command in TypeScript shelling out to `cliclick`, or
as Python `subprocess` calls), **preserve this sequence byte-for-byte
including the `w:60` waits and the modifier-release lines.**

---

## Prerequisites

- `cliclick` installed: `brew install cliclick`.
  Apple Silicon path: `/opt/homebrew/bin/cliclick`.
- Accessibility permission granted to the *invoking* app (Raycast,
  iTerm, whatever launches the script — not to `cliclick` itself).

## The copy preamble (run while the source app is focused)

```bash
CLICLICK="/opt/homebrew/bin/cliclick"

# 1) Sentinel — so we can detect copy actually fired, instead of pasting stale clipboard.
SENTINEL="__voiceitt_copy_sentinel_$RANDOM__"
printf '%s' "$SENTINEL" | pbcopy

# 2) Release any modifiers Sticky Keys may have latched from earlier typing.
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05

# 3) Sticky-Keys-proof Cmd+A then Cmd+C in the currently focused app.
#    w:60 = 60ms wait between key events. Required — without it the
#    keypress can fire before the modifier is registered. w:120 between
#    the two letter presses gives the source app a beat to actually
#    select-all before we ask for copy.
"$CLICLICK" kd:cmd w:60 t:a w:120 t:c w:60 ku:cmd

# 4) Poll up to ~1s for the clipboard to change off the sentinel.
CURRENT=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  CURRENT=$(pbpaste)
  if [ "$CURRENT" != "$SENTINEL" ] && [ -n "$CURRENT" ]; then
    break
  fi
  sleep 0.1
done

# 5) Bail loudly if copy never landed.
if [ "$CURRENT" = "$SENTINEL" ] || [ -z "$CURRENT" ]; then
  osascript -e 'display notification "Cmd+A/Cmd+C did not capture text." with title "<your script name>"'
  exit 1
fi
```

## The paste ritual (after activating the target app)

```bash
osascript -e "tell application id \"$TARGET_BUNDLE_ID\" to activate"

# Give the target app a beat to take focus. 0.15s is enough on the
# user's machine; bump to 0.25 if you see paste-into-wrong-app races.
sleep 0.15

# Re-release modifiers — `activate` can race with Sticky Keys
# re-latching Cmd. This is NOT redundant with step 2 above.
"$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true
sleep 0.05

# Sticky-Keys-proof Cmd+V. Bracketed paste (default in modern iTerm,
# bash, zsh, python REPL, amp, claude) preserves embedded newlines as
# literal text instead of executing each line.
"$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd
```

## What each magic value means

| Value | Why |
|---|---|
| `ku:cmd,alt,ctrl,shift,fn` | Force-release every modifier Sticky Keys might have latched. Cheap; do it before any synthetic input. |
| `w:60` between `kd:cmd` and `t:a`/`t:v` | macOS event loop needs this much to register the modifier-down before the keypress. Lower and the keypress arrives unmodified. |
| `w:120` between `t:a` and `t:c` | The source app needs a beat to actually select-all before we ask for copy. Lower and you sometimes copy a partial selection. |
| `sleep 0.15` between `activate` and the next `cliclick` | App activation is async; pasting too early lands in the previous app. |
| `sleep 0.05` after the second `ku:cmd,alt,...` | Lets the modifier-release event settle before we press them again. |

## Things to *not* do

- ❌ AppleScript `keystroke "v" using command down` — silently swallowed under Sticky Keys.
- ❌ Skipping the modifier-release lines because "they look redundant" — they aren't.
- ❌ Setting the waits to `0` to "make it faster" — you'll get intermittent failures that depend on system load.
- ❌ Adding `cliclick` itself to Accessibility instead of the invoking app — Accessibility is per-controlling-process, not per-binary.

## Verification ritual

Always test with **System Settings → Accessibility → Keyboard →
Sticky Keys ON**. The whole point of this code is Sticky-Keys-safe
behavior; testing with it off proves nothing.
