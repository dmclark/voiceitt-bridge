# PROJECT-SPEC — voiceitt-bridge

This is the current project spec for `voiceitt-bridge`: the workflow,
hard constraints, MVP/post-MVP boundary, endpoint contracts, and
answered architecture decisions. It is the durable source of truth.

---

## What this project does

The user dictates with **Voiceitt**, a Chrome-only dictation extension
for atypical speech. Voiceitt only runs inside Chrome on `http://`
origins, but the user needs dictated text to land in arbitrary local
macOS apps: terminals (especially `amp` / `claude` in iTerm), VS Code,
Slack, notes, browser textareas, and any other app that accepts paste.

The bridge provides:

- a local `http://localhost` scratchpad page where Voiceitt can write;
- optional LLM cleanup for dictated text;
- Raycast hotkeys that send the raw or cleaned text into target apps;
- Sticky-Keys-safe input synthesis for users who cannot rely on
  modifier-chord keyboard shortcuts.

LLM cleanup is a soft polish step: remove stutters, honor
"scratch that" self-corrections, format lists, and make light grammar
fixes. It must never execute the transcript as instructions, and it
must never block the send path when the LLM fails.

---

## MVP / post-MVP boundary

### MVP

- `bridge/serve.py` is the MVP HTTP server. It serves the scratchpad
  and owns the endpoint contract below.
- MVP Python may use third-party dependencies, but only through
  **`uv`** (`pyproject.toml` + lockfile), never bare `pip`.
- MVP code may be multi-file under `bridge/` when that buys clarity.
- Cleanup-at-send is driven by Raycast Script Commands and
  `bridge/voiceitt-transform.py`.
- Raycast remains Script Commands for the common target hotkeys.

### Deferred post-MVP re-architecture

Do not replace `bridge/serve.py` with FastAPI for MVP. The FastAPI app
and `src/voiceitt_bridge/` package are post-MVP work, triggered by
features that genuinely need an in-page lifecycle:

1. prompt picker / active-prompt sidecar in the scratchpad header;
2. in-page preview-and-edit of cleaned text before send;
3. per-utterance raw-vs-cleaned observability / diff UI;
4. a long-shot Voiceitt correction feedback loop, if Voiceitt ever
   exposes a programmatic correction-ingestion API.

When the post-MVP FastAPI app lands, `bridge/serve.py` stays as the
simple known-good fallback for bisection and local scratchpad use.

---

## Non-negotiables

These constraints are load-bearing. The lesson numbers point to the
full stories in [`salvage/notes/LESSONS-LEARNED.md`](./salvage/notes/LESSONS-LEARNED.md).

1. **Sticky-Keys-safe input synthesis only.** Use `cliclick` with the
   exact ritual in [`salvage/snippets/cliclick-paste-ritual.md`](./salvage/snippets/cliclick-paste-ritual.md).
   Never use AppleScript `keystroke … using command down`. [6, 7, 8, 9]
2. **Serve the scratchpad over `http://localhost`.** Never use
   `file://`, and do not open Chrome with `--app=`. Voiceitt refuses
   both alternatives. [1, 2]
3. **Wrap dictated text in `<TRANSCRIPT>…</TRANSCRIPT>` before any LLM
   call.** Without this, the LLM may execute utterances like "make a
   directory called src" instead of cleaning them up. [17]
4. **Fail open with raw text.** If cleanup fails or times out, raw
   dictated text must still land in the output/send path. [19]
5. **AI is off by default.** Persist the toggle in `localStorage`; URL
   `?ai=0|1` may override at open time. [22]
6. **Before any Cmd+A/Cmd+C, stamp the clipboard with a random
   sentinel and poll `pbpaste` for change.** This prevents stale
   clipboard pastes. [10]
7. **One Raycast hotkey per target, not one dispatcher.** Raycast
   steals focus when invoked, so "read the frontmost app at send time"
   is unreliable. [26]
8. **API keys live in shell env / env files, never in `localStorage` or
   served web code.** [18]
9. **`POST /load` is hard-capped:** 50 KB, UTF-8 only, and the path
   must resolve under `$HOME`. [25]
10. **Reload starts clean.** No auto-restore of loaded files; SSE is
    the only server-side loaded-state notification path. [24]

If a change appears to require violating one of these, stop and ask the
user instead of routing around it.

---

## Current repo layout

| Concern | Location |
|---|---|
| User-facing setup, daily flow, hotkey table | [`README.md`](./README.md) |
| Project spec, constraints, MVP/post-MVP split | [`PROJECT-SPEC.md`](./PROJECT-SPEC.md) |
| LLM system prompts | [`prompts/`](./prompts/) |
| Scratchpad page | [`web/`](./web/) |
| MVP HTTP server + transform CLI | [`bridge/`](./bridge/) |
| Raycast Script Commands | [`raycast/`](./raycast/) |
| Carried-over reference artifacts | [`salvage/`](./salvage/) |
| Parking lot and design notes | [`notes/`](./notes/) |
| Dev convenience scripts | [`scripts/`](./scripts/) |

`salvage/` is verbatim reference material, not a mutable directory.
Read from it freely; do not edit it.

---

## Endpoint contract

`bridge/serve.py` owns these endpoints. Do not change an existing
contract without matching updates in `web/script.js` and any Raycast
script that calls it.

| Method | Path | Body | Response / behavior |
|---|---|---|---|
| `GET` | `/` and static paths | — | Serve the scratchpad assets from `web/`. |
| `POST` | `/transform` | `{"text":"..."}` | Return cleaned text as `text/plain` on 200; return 5xx on transform failure so callers can fail open to raw text. |
| `POST` | `/load` | `{"path":"<abs or ~-relative>"}` | Load one file into the in-memory slot. Enforce ≤50 KB, UTF-8, under `$HOME`. |
| `GET` | `/file` | — | Return `{"path":"...","text":"..."}` or empty strings when no file is loaded. |
| `GET` | `/events` | — | SSE stream; emits `event: reload` on successful `/load` plus heartbeat comments. |
| `GET` | `/ai-state` | — | Return text `0` or `1`, mirroring the page's AI master toggle; default `0`. |
| `POST` | `/ai-state` | raw text `0` or `1` | Update the server-side AI toggle mirror. |

---

## Clipboard hygiene and paste strategies

Clipboard-based sends must use the sentinel + `cliclick` ritual from
[`salvage/snippets/cliclick-paste-ritual.md`](./salvage/snippets/cliclick-paste-ritual.md).

Per-target strategies:

| Bundle id | Strategy | Touches clipboard? |
|---|---|---|
| `com.googlecode.iterm2` | `iterm-write`: `tell application "iTerm2" to tell current session to write text "…" newline NO` | No |
| `com.microsoft.VSCode` | clipboard ritual; future save-and-restore wrapper | Yes |
| `com.tinyspeck.slackmacgap` | clipboard ritual; future save-and-restore wrapper | Yes |
| anything else | clipboard ritual by default | Yes |

The iTerm strategy intentionally bypasses clipboard and keystroke
synthesis on the paste step. `newline NO` is required so embedded
newlines survive and the user controls when to submit.

Zero-code mitigation: add Raycast to **Raycast Settings → Extensions →
Clipboard History → Excluded Apps** so Raycast Clipboard History does
not log dictation transitions.

Rejected general paste strategies:

- `cliclick t:"…"` typing: too fragile under Sticky Keys and modifier
  characters.
- AppleScript `keystroke`: fails under Sticky Keys and violates
  non-negotiable 1.
- Accessibility API value injection as the general fallback: unreliable
  for Electron and terminal views.
- Chrome-extension injection for destinations: the browser is the
  dictation source, not the primary paste destination.

---

## Future Raycast Extension and npm posture

Script Commands remain the MVP Raycast surface. If prompt preferences,
AI Extension tools, or a richer target map justify a Raycast Extension:

- use **pnpm v11+**, never `npm`;
- keep `strictDepBuilds: true`;
- pin `@raycast/api` and other deps exactly;
- audit every new dependency;
- never run `npm install` in this repo.

If `npm install` is accidentally run here, rotate `GOOGLE_API_KEY` and
any other machine-reachable secrets.

Hotkey commands should still exist for high-frequency targets even if
AI Extension tools are added. AI tools are useful for the long tail and
compositional requests, not as a replacement for deterministic hotkeys.

---

## Answered decisions

| Decision | Answer |
|---|---|
| Repo name | `voiceitt-bridge` |
| Raycast surface | Script Commands now; Extension later when it buys preferences / prompt UX |
| LLM provider | Start Gemini-only; design pressure for pluggable providers is post-MVP |
| Prompt picker | In-page dropdown first, Raycast preference UI later; both post-MVP |
| Git history migration | No; clean repo, old repo remains reference |

For new decisions of similar weight, ask the user before committing.

---

## Verification expectations

- **Raycast / paste-ritual changes:** manually smoke-test with Sticky
  Keys ON, end-to-end: dictate → cleanup/raw fallback → send-to-target.
  There is no automated substitute.
- **`web/` changes:** open in Chrome with Voiceitt attached. Confirm
  Voiceitt-write detection, faux-caret tracking, fail-open cleanup, and
  AI-off default behavior.
- **`bridge/` changes:** run focused endpoint checks on a free port,
  especially `/load` confinement and `/events` liveness.
- **post-MVP `src/` work:** add unit/integration coverage; the bash
  prototype had none and this is where that changes.
