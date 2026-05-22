# AGENTS.md — `web/` conventions

The Voiceitt scratchpad page. Vanilla HTML, CSS, and JavaScript. No
build step, no framework, no bundler, no preprocessor.

> Read [`../HANDOFF.md`](../HANDOFF.md) (non-negotiables 1–5, 17, 19,
> 22) and the Voiceitt-specific section of
> [`../salvage/notes/LESSONS-LEARNED.md`](../salvage/notes/LESSONS-LEARNED.md)
> (lessons 1–5, 17–22, 27–28) before changing anything here.

## Conventions

- **Three files, separate, top-level:** `index.html`, `styles.css`,
  `script.js`. No inline `<style>` blocks; no inline `<script>`
  bodies. If the JS grows past one file, use ES modules via
  `<script type="module">`, not a bundler.
- **No npm, no `package.json`, no `node_modules/` in this directory
  ever.** If a feature seems to require one, surface it as a
  decision; don't quietly add a build step.
- **Comment density:** match `salvage/bridge/script.js`. The page is
  small enough that explanatory comments dominate the code-to-noise
  ratio, and the next reader is always a future LLM with no context.
- **Atkinson Hyperlegible font + warm-white background + red 1-px
  faux caret.** These are accessibility decisions for the user, not
  aesthetics. See lessons 27–29.

## Things that look fine but break Voiceitt

- **`file://` for the page.** Voiceitt refuses any non-`http://`
  origin. Must be served by a local HTTP server. (Non-negotiable 2.)
- **Opening the page with `chrome --app=`.** Disables most extensions
  including Voiceitt. Open as a normal Chrome window. (Lesson 2.)
- **Treating Voiceitt writes like user input.** Voiceitt commits via
  `execCommand('insertHTML')`, which fires a synthetic (non-trusted)
  `paste` event followed by a trusted `input` event with
  `inputType: ''`. Use that pattern to latch
  `voiceittWriting = true` so manual edits don't re-trigger auto-LLM
  cleanup. (Lesson 3.)
- **Relying on the native textarea caret to scroll.**
  `execCommand('insertHTML')` does **not** scroll the caret into
  view. After every Voiceitt write you must compute the caret's pixel
  position via the mirror-element trick and nudge `scrollTop`.
  (Lesson 4 + the `MIRROR_PROPS` list in `script.js`.)
- **Putting `GOOGLE_API_KEY` in `localStorage`.** Forbidden. The LLM
  call round-trips through the local server so the key stays in the
  shell env. (Non-negotiable 8, lesson 18.)
- **AI on by default.** Off by default, persisted in `localStorage`,
  overridable via `?ai=0|1` on the URL. (Non-negotiable 5, lesson 22.)

## Verification

- Open in Chrome with the Voiceitt extension attached.
- Dictate a multi-utterance paragraph; confirm:
  - The faux red caret stays visible and tracks.
  - The output pane stays empty when AI is off (default).
  - Toggling AI on debounces 700 ms after the last `input` event,
    then populates the output pane with cleaned text.
  - If the LLM call fails (kill the server mid-dictation), the raw
    dictated text appears in the output pane — never an empty pane
    with an error toast. (Non-negotiable 4.)
- Reload the page: confirm no loaded-file state restores. (Lesson 24.)
