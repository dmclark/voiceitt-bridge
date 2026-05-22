# Salvage

Verbatim copies of artifacts from the `voiceitt-amp-bridge` prototype
worth carrying into the next-gen repo. Curated, not exhaustive — only
files that captured hard-won knowledge or working code that would take
non-trivial effort to recreate from a spec.

For the project vision and "where this is going next," see
[`../HANDOFF.md`](../HANDOFF.md).

For the "things we already tried and rejected" / "don't redo this"
list, see [`notes/LESSONS-LEARNED.md`](./notes/LESSONS-LEARNED.md).

---

## How to use this

You have two reasonable options:

1. **Copy `salvage/` into the new repo** as a top-level `legacy/` or
   `reference/` folder. The next-gen AI session reads from it the
   same way it would read any other file in the new repo.
2. **Point the next-gen AI session at this path directly**
   (`file:///Users/dzc86/voiceitt-amp-bridge/salvage/...`) and don't
   copy. Lighter-weight; downside is the AI's tools may struggle to
   read files outside the new repo's workspace.

The `HANDOFF.md` at the repo root is written assuming option 1.
Change paths if you go with option 2.

---

## Contents

### `prompts/`
- **`default.md`** — the post-transcription cleanup system prompt.
  Just polished (commit `a60b613`); the `<TRANSCRIPT>…</TRANSCRIPT>`
  framing here is load-bearing — see lesson 17.

### `bridge/` — the working scratchpad page + Python server
- **`serve.py`** — `ThreadingHTTPServer` with three responsibilities:
  static file serving, `POST /transform` (shells out to
  `voiceitt-transform`), and `POST /load` + `GET /events` (SSE
  push-channel for the Raycast file loader).
- **`dictate.html`** — two-pane layout (dictated / to-be-pasted),
  AI master-toggle, file-loader strip.
- **`script.js`** — the page logic. Notable: Voiceitt-write detection
  (`paste` + `input` event pattern, lesson 3), debounced
  `POST /transform`, fail-open behaviour, `EventSource('/events')` for
  live file reload, and the faux-caret implementation (lessons 4, 27, 28).
- **`styles.css`** — Atkinson Hyperlegible typography, warm-white
  background, red caret, focus font-size bump, faux-caret animation.

### `scripts/` — Raycast Script Commands worth porting
- **`open-voiceitt.sh`** — the boot sequence: source
  `~/.config/voiceitt-bridge/env`, raise the existing Chrome window if
  found (with optional URL nav for `?ai=0|1` mode override), otherwise
  start `serve.py` in the background + open a new Chrome window.
- **`send-to-vscode.sh`** — canonical `cliclick`-paste send-to-*
  shape (works for any app that accepts a normal Cmd+V into its
  focused control: VS Code, Slack, Notes, most editors). Start here
  when adding new targets.
- **`send-to-iterm.sh`** — same shape but with an AppleScript
  `tell current window … select` activation step. Use this pattern
  when you need to target a specific tab/session in a terminal-style
  app before pasting.
- **`load-file-to-scratchpad.sh`** — macOS `choose file` open-panel →
  `POST /load` round-trip, with friendly error notifications for
  413 / 415 / 403 / network failures.
- **`voiceitt-transform`** — bash + curl + jq call to Gemini. Likely
  to be replaced by ~50 lines of Python `urllib.request` in the new
  repo (parking lot 2026-05-20), but the prompt-loading logic,
  `<TRANSCRIPT>` framing, fail-mode handling (HTTP code capture via
  `-w` sentinel, curl-stderr capture, jq-error capture), and the
  `?ai=0|1` URL override convention are wisdom worth keeping.

### `snippets/`
- **`cliclick-paste-ritual.md`** — the Sticky-Keys-safe paste sequence,
  annotated. The single most important page in this entire salvage
  folder. Read this before writing any new keystroke synthesis code.

### `notes/`
- **`LESSONS-LEARNED.md`** — 37 numbered "we learned this the hard
  way" items. Voiceitt quirks, Sticky Keys workarounds, macOS
  automation permissions, LLM-transform design decisions, and a
  bottom-of-file "things we already tried and rejected" list.
- **`PARKING-LOT.md`** — unstructured ideas from the old repo. Not
  commitments; useful as a memory of what was considered.

---

## What is NOT in here, and why

- **`install.sh`** — specific to the symlink-based Script Commands
  install; obsolete once we move to either a Raycast Extension or a
  packaged Python app with its own installer.
- **`scripts/new-shortcut.sh`** — the bash generator; obsolete once
  targets become Extension commands defined in a `package.json`.
- **`scripts/back-to-voiceitt.sh`, `scripts/dictate.sh`,
  `scripts/dictate-ai.sh`** — thin wrappers around `open-voiceitt.sh`.
  Re-derive from the new architecture rather than carrying forward.
- **`README.md`** — too tied to the bash-pile architecture. The new
  repo's README will look very different.
- **`AGENTS.md`** — explicitly built around "no build step, no
  framework"; the new repo inverts that decision.
- **`notes/ROADMAP.md`, `notes/ERD.md`** — design documents written
  for the bash-pile design. The wisdom in them is mostly captured in
  `LESSONS-LEARNED.md`; the rest is design narrative that no longer
  applies. Read them in the original repo for context if you want, but
  do not let them shape new-repo decisions.
- **`notes/amp-cost-analysis.md`, `notes/notes-chrome-extension.md`** —
  excluded by `.gitignore` in the original repo; not safe to copy.
