# Lessons learned

Hard-won knowledge from the `voiceitt-amp-bridge` prototype. If you are
the AI building the next-gen repo, **read this before writing code that
touches dictation, clipboard, paste, Chrome, Voiceitt, or Raycast**.
Each item is here because the obvious thing did not work and we paid in
debugging time to discover the right thing.

---

## Voiceitt-specific

1. **Voiceitt only runs on `http://` origins, never `file://`.**
   The scratchpad must be served by a local HTTP server. We use port
   `7531` by convention; nothing depends on that number.

2. **Don't open the scratchpad with `chrome --app=`.** `--app` mode
   disables most extensions, including Voiceitt. Open a normal Chrome
   window with `open -na "Google Chrome" --args --new-window <url>` and
   identify it later by a unique `<title>`.

3. **Voiceitt commits each utterance via
   `execCommand('insertHTML')`.** This fires a synthetic (non-trusted)
   `paste` `ClipboardEvent` followed by a trusted `input` event with
   `inputType: ''`. Real keystrokes / user paste do not produce that
   pattern. Use it to detect "this is a Voiceitt write, not a user
   edit" by latching `voiceittWriting = true` on the untrusted paste
   and consuming it on the next `input` event. Manual edits should not
   re-trigger auto-LLM cleanup — that's a feature, not a bug.

4. **`insertHTML` does NOT scroll the caret into view.** Real
   keystrokes do; `execCommand('insertHTML')` and `value =` assignments
   do not. After every Voiceitt write you must compute the caret's
   pixel position (mirror-element trick) and nudge `scrollTop` when
   the caret falls outside the viewport. Without this, dictation past
   the visible pane silently scrolls off-screen.

5. **Voiceitt overlay cannot float over arbitrary macOS apps.** Chrome
   MV3 sandbox + Voiceitt's `document.hasFocus()` insertion gate kill
   Document Picture-in-Picture, window pinning, and click-through
   paths. Don't waste time trying. (See parking lot 2026-05-15.)

---

## Sticky Keys / macOS input synthesis

6. **Never use AppleScript `keystroke "v" using command down` for
   paste.** macOS Sticky Keys (used by many one-finger typists,
   including this user — it is the entire reason this repo exists)
   silently swallows or latches the synthetic Cmd. The paste either
   doesn't fire or leaves Cmd "stuck" so the next keypress triggers a
   menu shortcut.

7. **Use `cliclick` for all modifier-bearing keystrokes.** `cliclick`
   posts CGEvents at a layer below where Sticky Keys interferes.
   Install via `brew install cliclick`. On Apple Silicon it lives at
   `/opt/homebrew/bin/cliclick`.

8. **The Sticky-Keys-safe paste ritual is non-obvious.** Use exactly
   this sequence (see [snippets/cliclick-paste-ritual.md](../snippets/cliclick-paste-ritual.md)
   for the annotated version):
   ```bash
   "$CLICLICK" ku:cmd,alt,ctrl,shift,fn >/dev/null 2>&1 || true   # release any stuck modifiers
   sleep 0.05
   "$CLICLICK" kd:cmd w:60 t:v w:60 ku:cmd                        # press Cmd, wait 60ms, type 'v', wait 60ms, release Cmd
   ```
   The waits are not cosmetic. Without `w:60` the keypress can fire
   before the modifier is registered.

9. **Re-release modifiers after `osascript -e '... activate'`.** The
   app activation can race with Sticky Keys re-latching Cmd. Insert
   another `ku:cmd,alt,ctrl,shift,fn` + 50ms sleep between the
   `activate` and the paste.

10. **Stamp the clipboard with a sentinel before Cmd+A/Cmd+C.** macOS
    sometimes silently fails to capture (wrong app focused, focus
    race). Without a sentinel you'd paste whatever stale text was on
    the clipboard. The pattern is in every `send-to-*.sh`:
    ```bash
    SENTINEL="__voiceitt_copy_sentinel_$RANDOM__"
    printf '%s' "$SENTINEL" | pbcopy
    "$CLICLICK" kd:cmd w:60 t:a w:120 t:c w:60 ku:cmd
    # then poll pbpaste for up to ~1s waiting for it to change off the sentinel.
    ```

11. **Bracketed paste is the right default for terminals.** Modern
    iTerm + shells/REPLs (including `amp`, `claude`, `python`, `bash`)
    handle bracketed paste correctly, preserving embedded newlines as
    literal text. Do not press Return automatically unless the user
    explicitly opts in.

12. **iTerm's AppleScript `write text ... newline yes` mangles
    embedded newlines.** Don't use it. Use `cliclick` Cmd+V instead.
    This is documented in the AppleScript path of `send-to-iterm.sh`
    (preserved here for the "tell current session to select" pattern,
    which is still useful for activating the right tab).

13. **Secure Input mode blocks everything.** When a macOS password
    field is focused anywhere on the system, no synthetic input works
    — neither `cliclick` nor AppleScript. Detect with `ioreg` if you
    care; otherwise just fail loudly with a notification.

---

## Permissions

14. **Per-(controlling-app, controlled-app) automation prompts.** The
    first time a script tells, e.g., Slack to activate, macOS prompts
    *"Allow Raycast to control Slack?"*. Each new target app =
    one new prompt. This shows up under **System Settings → Privacy &
    Security → Automation**. Mention it explicitly in any
    add-a-new-target flow or the user will mistake the prompt for an
    error.

15. **Accessibility is per-controlling-app, not per-cliclick.** If
    `cliclick` is invoked from iTerm, Accessibility must be granted to
    *iTerm*. From Raycast, grant Raycast. Adding `cliclick` itself to
    Accessibility does nothing.

16. **Raycast inherits the user's shell env on launch.** This is why
    `GOOGLE_API_KEY` "just works" when set in `.zshrc`. But if Raycast
    is launched before login items finish, the env may be empty. The
    safer pattern is the `$VOICEITT_BRIDGE_DIR/env` file sourced
    inside `open-voiceitt.sh` — see that script.

---

## LLM transform

17. **Wrap dictated text in `<TRANSCRIPT>…</TRANSCRIPT>` before
    sending to the LLM.** Without the framing the LLM treats utterances
    like "make a directory called src" as instructions to execute
    rather than text to clean up. The matching system prompt
    (`prompts/default.md`) is built around this tag.

18. **Don't put the API key in the browser.** Doing the LLM call in
    `script.js` would force the key into `localStorage`. Round-trip
    through the local Python server (`POST /transform`) instead, so
    the key stays in the shell env.

19. **Fail open with raw text, never block.** If the LLM call fails,
    times out, or returns a non-200, drop the raw dictated text into
    the output pane and continue. The user is mid-dictation; never
    leave them with an empty output pane and a cryptic error.

20. **Debounce 700 ms after the last `input` event.** Shorter and you
    fire on every word; longer and the transform feels laggy after
    the user pauses speaking.

21. **`gemini-2.5-flash-lite` is the right v0 default** — typically
    sub-second; `flash` (no `-lite`) is 1–5s with outliers. Make the
    model env-configurable.

22. **AI off by default.** Auto-firing the LLM on every utterance is
    expensive and surprising. The master toggle in the scratchpad
    UI persists to `localStorage`; URL `?ai=0|1` overrides at open
    time (so Raycast can have separate `dictate` and `dictate-ai`
    commands).

---

## Architectural decisions worth keeping

23. **Server-Sent Events, not polling, for live-swap.** When the
    Raycast `Load File into Scratchpad` command runs in a different
    process from the page, the page needs a push channel. SSE
    (`EventSource` on `/events`, `Queue` per subscriber on the
    server, broadcast on `/load`, 15s heartbeat) is ~30 lines and
    auto-reconnects with backoff. WebSockets would be overkill for
    one event type in one direction.

24. **Single in-memory load slot, no history, no auto-restore on
    reload.** The user's mental model is "reload starts clean."
    Multi-file / recent-files dropdown is intentionally parked.

25. **Hard caps on the load endpoint.** 50 KB max, UTF-8 only, path
    must resolve under `$HOME`. Without the `$HOME` check a stray
    `POST /load` can slurp `/etc/...`.

26. **One Raycast hotkey per target, not one dispatcher.** Triggering
    the Raycast hotkey itself changes focus, so "read frontmost app
    at send time" cannot work — the target must be fixed ahead of
    time. Per-target scripts also let macOS's per-(app, app)
    permission prompts surface exactly once per target.

27. **Faux caret for visibility.** The native textarea caret is
    hard-coded to 1px in every browser; there is no `caret-width`.
    Hide the native caret on `:focus`, overlay a 3px `<div>` whose
    position is computed from a hidden mirror element that mirrors
    the textarea's text + computed styles up to `selectionStart`.
    Same trick CodeMirror / Monaco use. The mirror's `MIRROR_PROPS`
    list in [script.js](../bridge/script.js) is the bit that matters.

28. **High-contrast caret colour (macOS system red `#ff3b30`).** On a
    warm-white scratchpad background, a red 1-px caret is *much*
    easier for a low-vision dictator to spot than the default black
    one. This is the single biggest "where did I leave off?" win;
    everything else (faux caret, focus font-size bump, focused-pane
    tint) is incremental.

29. **Atkinson Hyperlegible font.** Designed for low-vision use,
    OFL-licensed, free on Google Fonts. Thematic + functional fit for
    a dictation tool. Fallback chain stays system-native.

---

## Things we already tried and rejected

30. **`chrome --app=` for the scratchpad.** Breaks Voiceitt
    (extensions disabled).
31. **`file://` for the scratchpad.** Breaks Voiceitt (no real origin).
32. **AppleScript `keystroke ... using command down` for paste.**
    Breaks under Sticky Keys.
33. **iTerm `write text ... newline yes`.** Mangles embedded newlines.
34. **API key in `localStorage`.** Security smell + redundant with
    shell env.
35. **Auto-restore loaded file on page reload.** Confusing — violates
    "reload starts clean."
36. **Multi-file load / recent-files dropdown.** Premature; parked.
37. **Voiceitt overlay floating over arbitrary apps.** Infeasible per
    parking lot 2026-05-15.
