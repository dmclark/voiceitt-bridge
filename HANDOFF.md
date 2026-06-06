# HANDOFF — voiceitt-amp-bridge → next-gen repo

You (the AI in the new repo) are inheriting a prototype that proved out
a specific dictation workflow. This document is the **spec** for the
next-gen repo, plus a curated pointer to the **salvageable code** from
the prototype. Read this entire file before writing any code.

The prototype is preserved as a reference; do not assume its
architecture, file layout, or conventions carry over.

---

## What this project is, and what it is *now becoming*

### The user's actual workflow

The user dictates with **Voiceitt** (a Chrome-only voice dictation
extension built for atypical speech). Voiceitt only runs inside
Chrome on `http://` origins. The user needs to land dictated text in
**arbitrary local macOS apps** — terminals (especially `amp` / `claude`
running in iTerm), editors (VS Code), chat (Slack), notes, browser
textareas elsewhere — without ever touching the keyboard for
modifier-chord shortcuts (the user relies on macOS Sticky Keys).

The user also wants the dictated text **cleaned up by an LLM** before
it lands in the destination: stutter removal, "scratch that"
self-corrections honored, list formatting, light grammar fixes — but
never executed as instructions, and always with a fail-open path so
the LLM is a soft polish, not a hard dependency.

> **Decision (MVP / post-MVP split) — revised 2026-06-06:**
>
> **Reversal:** the original rule that "MVP ships *no Python
> architecture*" is **withdrawn**. MVP may now use Python freely —
> third-party dependencies are allowed (managed with **`uv`**, never
> bare `pip`; a `pyproject.toml` + lockfile are legitimate MVP
> artifacts) and multi-file Python is fine. The line that still holds
> is narrower: **`bridge/serve.py` stays the MVP server — it is not
> replaced by FastAPI for MVP.** What remains post-MVP is the
> *re-architecture*, not "Python" as such.
>
> - **MVP.** Cleanup runs at send-time via `raycast/voiceitt-transform` (bash + curl + jq, carried over verbatim from the prototype; porting it to a small Python module — under `bridge/`, with `uv`-managed deps if useful — is now permitted MVP work, not a post-MVP trigger). The `send-to-*` Raycast hotkeys shell out to it and then drop the cleaned text into the target app via the sentinel + cliclick paste ritual (or, for iTerm, AppleScript `write text … newline NO`). The scratchpad page itself is served by `bridge/serve.py` — the prototype's `ThreadingHTTPServer`, carried over and free to grow `uv`-managed deps or split into multiple files under `bridge/` where that buys something. The four-endpoint contract (`/transform`, `/load`, `/file`, `/events`) is MVP, implemented in `bridge/serve.py`.
> - **post-MVP — deferred.** The FastAPI re-architecture described in the rest of this doc (FastAPI `/transform` + pluggable provider, the `src/voiceitt_bridge/` package, prompt loader and framing helper as package modules) lands when *Slot-A-only* capabilities — ones that fundamentally require the in-page lifecycle, not the send-time path — become worth the build cost. The **primary triggers are all in-page UX wins, each genuinely valuable on its own and any one sufficient to justify the module:** (1) a **prompt-picker / active-prompt sidecar** in the scratchpad header so the user can switch cleanup styles per session without leaving the dictation flow; (2) **in-page preview-and-edit** of the cleaned text before the send-to-* hotkey fires; (3) **per-utterance observability / diff UI** showing raw vs. cleaned (essential when the LLM "helpfully" rewrites something the user meant literally). A **secondary, long-shot trigger** is the **Voiceitt correction feedback loop**: round-tripping raw and cleaned transcripts back to Voiceitt for personalised model training. That's structurally impossible from a Raycast AI Command — by the time `{clipboard}` is populated, the original Voiceitt browser context is gone — so the in-page module is the only place this *could* land. But it depends on Voiceitt exposing a programmatic correction-ingestion surface, which they do not today and may never; treat it as a happy bonus if it ever materialises, not as the reason to build.
> - When the post-MVP FastAPI app lands, `bridge/serve.py` does not go away — it stays as the simple known-good fallback (useful for bisection and for "just run the page locally" workflows). The two are not mutually exclusive.
>
> Treat this document's FastAPI sections (the FastAPI app, the `src/voiceitt_bridge/` package layout, pluggable-provider dispatch, prompt-picker plumbing) as the *post-MVP destination*. Everything else Python — `uv`-managed deps, multi-file code under `bridge/`, a Python rewrite of `voiceitt-transform`, and tests — is fair game for MVP. The four-endpoint contract itself (`/transform`, `/load`, `/file`, `/events`) is MVP, implemented in `bridge/serve.py`. (The 2026-05-22 `salvage/notes/PARKING-LOT.md` entry that deferred the Python transform module is superseded by this reversal.)

#### MVP first-PR scope

> **Superseded for current work (2026-06-06):** the no-Python-architecture constraint this section was written under has been withdrawn — see the revised decision blockquote above. The text below is kept as a record of what the early PRs actually did, **not** as a rule to keep following; in particular, "omit every Python directory and file" describes the merged phase-0 scope, not a current prohibition on `uv`-managed deps, `pyproject.toml`, multi-file Python, or tests.
>
> **Historical note (kept verbatim):** the original first PR (`feat/phase-0-scaffold`, merged) executed the scope below as written. A subsequent PR (`feat/carry-serve-py-forward`) extended MVP to also include `bridge/serve.py` (the prototype's stdlib `ThreadingHTTPServer`), so the repo became standalone for net-new users without the prototype installed. The "omit every Python directory and file" clause in item 1 below should therefore read as "omit every Python *architecture* file (FastAPI app, `src/voiceitt_bridge/`, `pyproject.toml`, `tests/`)" — the single-file stdlib server is allowed under the revised reading of "no Python in MVP". See the decision blockquote above for the current rule.

Concretely, the first PR in this repo should do the following — and **only** the following:

1. **Scaffold the directory layout** per the "Repo layout" section below, but **omit every Python directory and file** (`src/`, `tests/`, `pyproject.toml`, `uv.lock`). Create: top-level `README.md`, root `AGENTS.md`, `web/` (with its own `AGENTS.md`), `raycast/` (with its own `AGENTS.md`), `prompts/`, `notes/`, `scripts/`.
2. **Carry the salvage forward verbatim, then adapt minimally:**
    - `salvage/prompts/default.md` → `prompts/default.md` (unchanged)
    - `salvage/bridge/{dictate.html, script.js, styles.css}` → `web/{index.html, script.js, styles.css}` (rename only; the separation-of-files convention is already satisfied)
    - `salvage/scripts/{send-to-*.sh, open-voiceitt.sh, load-file-to-scratchpad.sh}` → `raycast/` (unchanged)
    - `salvage/snippets/cliclick-paste-ritual.md` is the byte-for-byte reference any new `send-to-*` code must match.
3. **Land the MVP cleanup-at-send path.** Two acceptable shapes — pick whichever closes a clean user-flow loop, document the choice in `README.md`:
    - **(a) Raycast AI Command** wrapping `{clipboard}` in `<TRANSCRIPT>…</TRANSCRIPT>` and pulling rules from `prompts/default.md`. Validate against current Raycast docs that the invocation surface actually round-trips cleanly back into the paste step — AI Commands return results into Raycast's UI, not back to a calling script, so the end-to-end ergonomics need to work out.
    - **(b) Carry `salvage/scripts/voiceitt-transform` forward verbatim** into `raycast/` and have the `send-to-*.sh` commands shell out to it. ~150 lines of bash + curl + jq, already proven, no Raycast dependency. This is the safe fallback if (a) doesn't close cleanly.
4. **Implement the iTerm paste-strategy win** (per "Clipboard hygiene and paste strategies" below): replace the clipboard ritual in `raycast/send-to-iterm.sh` with `tell application "iTerm2" to tell current session to write text "…" newline NO`. Other targets keep the existing clipboard ritual for this PR.
5. **Document the zero-code clipboard-hygiene mitigation in `README.md`:** instruct the user to add Raycast to **Settings → Extensions → Clipboard History → Excluded Apps**.
6. **Conventional Commits, topic branch** (e.g. `feat/mvp-scaffold`), one logical change per commit. **Do not push** without asking.

Explicitly **out of scope** for this PR: FastAPI app, `src/voiceitt_bridge/`, `pyproject.toml`, `tests/`, the `clipboard-restore` save-and-restore wrapper (next PR), any Raycast Extension work, prompt-picker UI. All of these come later — most of them in post-MVP.

Before opening the PR, surface for the user:
- The (a) vs (b) decision in step 3, with your recommendation.
- The target bundle ids in the paste-strategy map — confirm they're correct for this machine.
- Whether the iTerm `write text` swap should be smoke-tested with a multi-line cleaned transcript before the PR is considered ready.

### Architectural shift from the prototype

The prototype was a deliberate "pile of bash + one HTML file":

```diagram
╭──────────────────╮  HTTP   ╭──────────────────╮  pbcopy   ╭──────────────╮
│ Chrome           │────────▶│ Local Python     │──────────▶│ macOS        │
│ + Voiceitt       │         │ http.server      │           │ clipboard    │
│ → scratchpad     │         │ (serve.py)       │           ╰──────┬───────╯
╰──────────────────╯         ╰─────────┬────────╯                  │ cliclick Cmd+V
                                       │ shells out to             ▼
                                       │ voiceitt-transform   ╭──────────────╮
                                       │ (bash + curl + jq)   │ Target app   │
                                       ▼                      │ (any)        │
                              ╭──────────────────╮            ╰──────────────╯
                              │ Gemini API       │
                              ╰──────────────────╯

Raycast Script Commands (bash, header-comment metadata) drive the
clipboard → target-app paste step, one per target app.
```

The next-gen repo flips two of those decisions:

1. **The Python piece becomes a real web app**, not a hand-rolled
   `http.server` subclass. Pick a small modern Python web framework
   (FastAPI is the obvious fit given the existing `POST /transform` +
   `POST /load` + SSE `GET /events` shape — async support, ergonomic
   JSON, native SSE-friendly via `StreamingResponse`).
> A: use FastAPI
2. **The Raycast piece stays Script Commands for now, with a planned
   flip to a Raycast Extension** when the user reaches the prompt
   picker / active-prompt sidecar work that requires a preferences
   UI. (See "Open decision" below — confirm with the user before
   committing either way.)

```diagram
╭────────────────────────────╮         ╭────────────────────────────╮
│ Python web app             │◀───────▶│ Raycast Extension (TS)     │
│ (FastAPI)                  │  HTTP   │ — or — Script Commands     │
│ — replaces serve.py        │         │ — drives clipboard → target│
│ — owns /transform, /load,  │         │ — keeps cliclick paste     │
│   /events, /file, prompts  │         │   ritual byte-for-byte     │
╰────────────────────────────╯         ╰────────────────────────────╯
            ▲
            │ stdin/stdout (or in-process import)
            ▼
╭────────────────────────────╮
│ Transform module           │
│ (replaces voiceitt-transform)│
│ — pluggable LLM provider   │
│ — owns prompt picker       │
│ — fail-open by contract    │
╰────────────────────────────╯
```

---

## Non-negotiables (read these once, then **never violate them**)

These are not preferences. They are hard-won constraints. Each comes
with a numbered entry in [`salvage/notes/LESSONS-LEARNED.md`](./salvage/notes/LESSONS-LEARNED.md);
the number in brackets points to the full story.

1. **Sticky-Keys-safe input synthesis only.** Use `cliclick` with the
   exact ritual in [`salvage/snippets/cliclick-paste-ritual.md`](./salvage/snippets/cliclick-paste-ritual.md).
   Never use AppleScript `keystroke … using command down`. [6, 7, 8, 9]
2. **Scratchpad must be served over `http://localhost`**, not
   `file://`, and Chrome must be launched as a *normal* window, not
   with `--app=`. Voiceitt refuses both alternatives. [1, 2]
3. **Wrap dictated text in `<TRANSCRIPT>…</TRANSCRIPT>` before sending
   to any LLM.** The system prompt in
   [`salvage/prompts/default.md`](./salvage/prompts/default.md) is
   built around this tag, and dropping it causes the LLM to *execute*
   utterances like "make a directory called src" instead of cleaning
   them up. [17]
4. **Fail open with raw text, never block.** If the LLM call fails or
   times out, the raw dictated text must land in the output pane and
   the send-to-* hotkey must continue to work. [19]
5. **AI off by default, persisted in `localStorage`**, with URL
   `?ai=0|1` overrides at open time. [22]
6. **Stamp the clipboard with a random sentinel before any Cmd+A/Cmd+C**
   and poll `pbpaste` for change before pasting. Pasting stale
   clipboard contents is the single most common silent failure. [10]
7. **One Raycast hotkey per target, not one dispatcher.** Triggering
   the Raycast hotkey itself steals focus, so "read frontmost app at
   send time" cannot work. [26]
8. **API keys live in the shell env, never in `localStorage`.** The
   transform call must round-trip through the local server. [18]
9. **`POST /load` is hard-capped**: 50 KB, UTF-8 only, path must
   resolve under `$HOME`. [25]
10. **Reload starts clean.** No auto-restore of loaded files; SSE is
    the only path that surfaces server-side `_loaded` state. [24]

If you find yourself wanting to do any of these "just this once" —
stop, re-read the lesson, and pick a different approach.

---

## Spec for the new repo

### Tech choices

| Layer | Pick | Why |
|---|---|---|
| Python web framework | **FastAPI** | Async-friendly for SSE, ergonomic JSON, typed request models, well-documented. Existing endpoints (`/transform`, `/load`, `/events`, `/file`) map 1:1. |
| Package/env manager | **`uv`** | Fast, modern, single binary, lock-file in repo. (If the user prefers `poetry` or `hatch`, defer to them.) |
| Lint / format | `ruff` (lint + format both) | One tool, fast. |
| Type checker | `mypy --strict` on `src/`, lenient on tests | Catch dict-shape errors early. |
| Tests | `pytest` + `httpx.AsyncClient` for endpoint tests | The bash prototype had no tests; this is the moment to add them. |
| LLM transform | Start with Google Gemini 2.5 Flash Lite via `urllib.request` *or* the official `google-genai` SDK. Design for **pluggable providers** from day one (the `voiceitt-transform` parking-lot note flagged this). | Multi-provider was deferred in the prototype because bash made it painful; Python makes it easy. |
| Raycast side | **Start with Script Commands** (carried over from the prototype). Flip to a **Raycast Extension** when the user reaches prompt-picker / preferences work. | Avoid paying the Node/TS/build cost until it buys something the user actually needs. |
| Node package manager (only if/when the Extension is built) | **`pnpm` v11+ with default `strictDepBuilds: true`** — never `npm`. | Since Sep 2025 the npm ecosystem has been hit by a series of self-replicating worms (Shai-Hulud and successors) that propagate via `preinstall`/`postinstall` lifecycle scripts running automatically on `npm install`. pnpm v11 blocks lifecycle scripts by default, enforces a release cooldown on new versions, and requires explicit allowlisting of packages that need build steps. Bun and Yarn Berry have similar consumer-side defenses; the npm CLI does not. See "npm supply chain posture" section below. |

#### Why not Node (or Bun) on the server, for language unification?

Considered and rejected. The case *for* — one language across server
and Extension, shared types, shared business code — sounds appealing
but is weak in this specific project:

1. **It would double the npm exposure surface.** The Extension's
   `node_modules/` is unavoidable but small (`@raycast/api` + a
   couple of utility deps). Putting the server on Node means a
   *second* npm tree, larger (HTTP framework, SSE handler, LLM SDK,
   logging), running on the user's machine with `GOOGLE_API_KEY`
   and other secrets in its env. Every transitive dep becomes a
   `preinstall`-hook attack surface against those secrets. See
   "npm supply chain posture" below.
2. **Shared-code payoff is tiny.** The `<TRANSCRIPT>` wrapper is
   3 lines; request/response types are ~10; the prompt loader is
   15 lines whose file paths differ between server-side and
   Extension-side anyway. Not enough to justify language unification.
3. **Python keeps "no build step" on the server.** `python serve.py`
   and you're running. Node means `tsc` or `tsx`/`ts-node` (another
   dep). Bun fixes that but still uses the npm registry.
4. **The existing `serve.py` works.** Port to FastAPI is mechanical;
   rewriting in Node is a green-field re-implementation.
5. **Performance is irrelevant at this scale.** Single user,
   ~1 req/sec peak. FastAPI/uvicorn and Node/Fastify both handle
   this in their sleep.
6. **Subprocess shape is identical either way.** `pbcopy`,
   `pbpaste`, `osascript`, and `cliclick` are subprocess calls in
   either language. Wash.

**If you want type-level unification with the Extension**, do it
the right way: FastAPI generates OpenAPI for free; have the
Extension's build step generate TS types from that schema. Stronger
guarantees than hand-mirroring types, and no language compromise.

### Repo layout (proposed; confirm with user)

```
voiceitt-bridge/                        # new repo name — drop "amp" / "iterm"
├── README.md                           # user-facing setup, hotkey table, troubleshooting
├── AGENTS.md                           # root routing doc; per-dir AGENTS.md beneath
├── pyproject.toml                      # uv / hatchling
├── uv.lock
├── src/
│   └── voiceitt_bridge/
│       ├── __init__.py
│       ├── app.py                      # FastAPI app factory
│       ├── routes/
│       │   ├── transform.py            # POST /transform
│       │   ├── load.py                 # POST /load, GET /file
│       │   ├── events.py               # GET /events  (SSE)
│       │   └── static.py               # serve the scratchpad assets
│       ├── transform/
│       │   ├── __init__.py             # Transformer protocol + dispatch
│       │   ├── gemini.py               # Gemini provider
│       │   ├── prompts.py              # prompt-file loader, picker
│       │   └── framing.py              # <TRANSCRIPT> wrap/unwrap
│       ├── config.py                   # env-var loading, paths
│       └── logging.py
│       └── AGENTS.md                   # python conventions
├── web/                                # the scratchpad page
│   ├── index.html
│   ├── script.js
│   ├── styles.css
│   └── AGENTS.md                       # vanilla-JS conventions; no build step
├── raycast/                            # Raycast Script Commands (or future Extension)
│   ├── open-voiceitt.sh
│   ├── send-to-vscode.sh
│   ├── send-to-iterm.sh
│   ├── load-file-to-scratchpad.sh
│   ├── lib/                            # shared bash helpers (sentinel preamble, etc.)
│   │   ├── copy-focused.sh
│   │   └── paste-into.sh
│   └── AGENTS.md                       # raycast conventions; paste-ritual rules
├── prompts/                            # post-transcription prompts
│   └── default.md
├── tests/
│   ├── test_transform.py
│   ├── test_load.py
│   ├── test_events.py
│   └── fixtures/
├── scripts/                            # dev convenience (run server, lint, format)
│   └── dev.sh
└── notes/                              # parking lot, design notes
    └── PARKING-LOT.md
```

The `web/` directory is deliberately framework-free vanilla JS — the
scratchpad page is small, has no build pipeline, and benefits from
zero opinion. Keep it that way unless the page genuinely outgrows it.

> File structure approved 

### Endpoints (carry over verbatim)

| Method | Path | Body | Behavior |
|---|---|---|---|
| `GET`  | `/` and `/index.html` | — | Serve the scratchpad page from `web/`. |
| `POST` | `/transform` | `{"text": "…"}` | Wrap in `<TRANSCRIPT>`, send to LLM with system prompt, return cleaned text as `text/plain`. Fail open by returning a 5xx that the page treats as "use raw text". |
| `POST` | `/load` | `{"path": "/abs/path"}` | Read file (≤50 KB, UTF-8, under `$HOME`), store in in-memory `_loaded` slot, broadcast SSE `reload` event. |
| `GET`  | `/file` | — | Return current `_loaded` slot as `{"path": "...", "text": "..."}`. |
| `GET`  | `/events` | — | SSE stream; emits `event: reload` on `/load`; 15s heartbeat comments. |

Add new endpoints as needed; do not change the contracts of these
without coordinating a matching change in `web/script.js` and any
Raycast script that calls them.

### Configuration

All via env vars, with sane defaults:

| Env var | Default | Purpose |
|---|---|---|
| `VOICEITT_BRIDGE_PORT` | `7531` | Listen port. |
| `VOICEITT_BRIDGE_DIR` | `~/.config/voiceitt-bridge` | Runtime config dir (env file, prompts/, server.log). |
| `VOICEITT_TRANSFORM_MODEL` | `gemini-2.5-flash-lite` | LLM model id. |
| `VOICEITT_TRANSFORM_TIMEOUT` | `6` | Per-call seconds. |
| `VOICEITT_TRANSFORM_HARD_TIMEOUT` | `10` | Outer subprocess cap (only relevant if the transform stays a subprocess; once it's in-process, drop this). |
| `GOOGLE_API_KEY` | — | Required when the Gemini provider is selected. |

Source `$VOICEITT_BRIDGE_DIR/env` from the Raycast `open-voiceitt.sh`
wrapper so secrets land in the server's env even when Raycast didn't
inherit them from `.zshrc`. See `salvage/scripts/open-voiceitt.sh`.

### Conventions

- **Python**: `ruff format` on save, `ruff check --fix`, `mypy --strict`.
  Docstrings on every public function/class. Type-annotate everything.
- **Web** (in `web/`): vanilla, no build step, no framework, no
  bundler, no CSS preprocessor. Keep HTML, CSS, and JS in separate
  files (`index.html`, `styles.css`, `script.js`) — no inline
  `<style>` blocks, no inline `<script>` bodies. Use ES modules via
  `<script type="module">` if the JS grows to multiple files. Match
  the comment density of `salvage/bridge/script.js` — the page is
  small enough that explanatory comments dominate the
  code-to-noise ratio.
- **Bash** (in `raycast/`): `set -e` at top, numbered comments per
  step, `osascript <<'EOF' ... EOF` heredocs for AppleScript,
  cliclick path constant at the top.
- **Commits**: Conventional Commits (`feat`, `fix`, `docs`, `chore`,
  `refactor`, `test`, etc.). Topic branches: `<type>/<slug>`.

### Verification (no automatic substitute exists for these)

1. **Unit/integration tests** for everything in `src/` and `web/`
   logic. The bash prototype had none; the Python version has no
   excuse.
2. **Manual smoke test with Sticky Keys ON** for any change to
   `raycast/` or the paste-ritual code. There is no test framework
   for this; document the steps in `AGENTS.md`.
3. **Dictate-then-send round-trip** end-to-end before declaring any
   Raycast change done.

### Clipboard hygiene and paste strategies

Every dictated send is a clipboard write under the prototype's current
ritual (lesson 10: sentinel + poll + `cliclick kp:cmd+v`). Over a
heavy dictation day, that pollutes the user's clipboard history
(Raycast Clipboard History, Alfred, Pastebot, etc.) with dozens of
useless intermediate entries and overwrites whatever the user
actually had on the clipboard. Mitigate per-target, not blanket.

**Per-target paste strategies — encode as a map driving the shared
`pasteIntoApp(bundleId, opts)` chokepoint:**

| Bundle id | Strategy | Touches clipboard? |
|---|---|---|
| `com.googlecode.iterm2` | `iterm-write` — `tell application "iTerm2" to tell current session to write text "…" newline NO` | No |
| `com.microsoft.VSCode` | `clipboard-restore` — current ritual + save-and-restore wrapper | Yes (transient) |
| `com.tinyspeck.slackmacgap` | `clipboard-restore` | Yes (transient) |
| anything else | `clipboard-restore` (default) | Yes (transient) |

The iTerm branch is the highest-value swap because iTerm running
`amp` / `claude` is the user's #1 destination. `write text … newline
NO` is atomic, fast, supported by iTerm2's published AppleScript
dictionary, and bypasses both the clipboard and any keystroke
synthesis (so it sidesteps Sticky Keys entirely — non-negotiables 1,
6–9 don't even come into play on this path).

**Save-and-restore wrapper (the `clipboard-restore` strategy):**

```diagram
╭───────────────────────────────────────────────╮
│ 1. OLD=$(pbpaste)                             │
│ 2. stamp sentinel, set clipboard to new text  │
│ 3. cliclick kp:cmd+v   (lesson-10 ritual)     │
│ 4. sleep ~150 ms (let paste land)             │
│ 5. printf '%s' "$OLD" | pbcopy                │
╰───────────────────────────────────────────────╯
```

Caveats for step 1/5: skip the restore when `pbpaste` returns empty
or non-text (image, file ref). Doing this naively will turn a
copied PNG into stringified garbage. Clipboard *history* tools
(Raycast, Alfred) still log every transition — restore only fixes
the *current* clipboard, not the history. For history pollution
itself, see the Raycast settings tweak below.

**Zero-code mitigation worth doing first:** add Raycast (and, once
it exists, the bridge's own extension bundle id) to **Raycast
Settings → Extensions → Clipboard History → Excluded Apps**. This
stops Raycast's own clipboard history from logging the dictation
flow, which is probably the majority of the perceived pollution if
the user uses Raycast Clipboard History as their primary clipboard
manager. Document this in the repo's `README.md` setup steps.

**Considered and rejected** (do not re-litigate without strong new
evidence):

- **`cliclick t:"…"` (type-instead-of-paste).** Synthesizes
  per-character keystrokes including modifier-bearing chars
  (capitals, symbols, smart-quotes / em-dashes that the LLM
  cleanup loves to produce). That is precisely the attack surface
  Sticky Keys turns into latched-modifier chaos. Direct violation
  of non-negotiables 1, 6–9. Also slow and keyboard-layout /
  IME-fragile.
- **AppleScript `keystroke "…"`.** Same Sticky-Keys problem;
  already forbidden by non-negotiable 1.
- **Accessibility-API (`AXUIElement`) value-injection as a
  general default.** Works reasonably in Cocoa-native fields,
  fails uniformly in Electron and in terminal views (iTerm's
  terminal isn't an `AXTextArea`). The "general fallback" framing
  collapses on contact with the actual target mix.
- **A Chrome-extension injection path for browser targets.** The
  user does not paste *back into* the browser — the browser is
  the dictation *source* (Voiceitt scratchpad), not a destination
  — so the Chrome-side path has no caller.

**Phased rollout:**

1. **MVP, zero code:** add Raycast itself to Clipboard History's
   Excluded Apps. May resolve the visible problem entirely.
2. **MVP or 1, small effort, big win:** implement the
   `iterm-write` branch in `pasteIntoApp`. Retires the
   highest-volume polluter and improves reliability simultaneously.
3. **Whenever the clipboard-paste path next gets touched:** wrap
   the existing ritual with save-and-restore. ~10 lines of shell
   (Script Commands) or TS (Extension), gated on `pbpaste`
   returning text.

---

### npm supply chain posture (only relevant if you build the Extension)

If and when the Raycast side becomes an Extension, you'll have a
`package.json` and a `node_modules/`. That tree is the highest-risk
surface in the entire project. Treat it accordingly:

1. **Use `pnpm` v11+, never `npm`.** Initialize with
   `pnpm init` and commit `pnpm-lock.yaml`. Do not install with
   `npm install` "just for convenience" — it'd silently bypass the
   defenses below.
2. **Leave `strictDepBuilds: true` on.** This blocks
   `preinstall` / `postinstall` / `prepare` lifecycle scripts by
   default. The first time you install a dep that legitimately needs
   a build step (e.g. `esbuild`), pnpm will prompt; allowlist it
   explicitly in `pnpm-workspace.yaml` under
   `onlyBuiltDependencies`. The expected count for a Raycast
   Extension is small (single digits).
3. **Keep the release cooldown on.** Default in pnpm v11 quarantines
   newly-published versions for a configurable window. Worth the
   slight install lag.
4. **Pin `@raycast/api` and every other dep to exact versions** in
   `package.json` (no `^`, no `~`). Trust the lockfile, not the
   range.
5. **Audit on every dep add.** Run `pnpm audit` and, if you have it,
   a third-party scanner like Socket. Don't add a dep without
   reading what it does.
6. **Rotate `GOOGLE_API_KEY` (and any other secret reachable from
   your dev machine) immediately if you ever accidentally run
   `npm install` on this repo.** The "I'll just `npm install` once
   to try something" path is exactly how Shai-Hulud spread.
7. **CI installs use `pnpm install --frozen-lockfile`.** Never
   resolve fresh in CI.

Context (so future-you remembers why these rules exist): since
September 2025 the npm registry has been hit by a continuing series
of self-replicating supply-chain worms — Shai-Hulud, Shai-Hulud 2.0,
Mini Shai-Hulud, and the May 2026 TanStack wave. They propagate by
hijacking the `preinstall` hook to harvest npm tokens, GitHub PATs,
and shell-env secrets (yes, including `GOOGLE_API_KEY`), then publish
infected versions from the victim's account. The npm CLI runs these
hooks automatically with no opt-in. pnpm with the defaults above
blocks the propagation vector. None of this is a silver bullet — the
May 2026 wave produced packages with valid SLSA provenance because
the worm hijacked the build pipeline itself — but it raises the bar
substantially.

### AI Extensions vs per-target hotkey commands (Extension-only)

If/when you build the Raycast Extension, you'll have the option to
expose **AI Extension tools** — functions Raycast AI can call when
the user phrases a request in natural language ("send this to Slack",
"paste it into whichever app I was just in"). Do not treat AI
Extensions as a *replacement* for per-target hotkey commands. They
are a different invocation pathway on top of the same paste code,
not a substitute for it.

**Build both, share one implementation:**

```diagram
╭─────────────────────╮     ╭──────────────────────────╮
│ Hotkey commands     │     │ AI Extension tools       │
│ Send to iTerm       │     │ "send to <app>"          │
│ Send to VS Code     │     │ "paste with X prompt..." │
│ Send to Slack       │     │ "send to where I was"    │
╰──────────┬──────────╯     ╰────────────┬─────────────╯
           │                             │
           ▼                             ▼
        ╭──────────────────────────────────────╮
        │ pasteIntoApp(bundleId, opts)         │
        │ — sentinel + cliclick paste ritual   │
        │ — per-app activation quirks          │
        ╰──────────────────────────────────────╯
```

**Use hotkey commands for** the 3–5 targets the user fires constantly
(iTerm, VS Code, the current chat app). These are sub-second,
deterministic, and don't interrupt mid-dictation flow.

**Use AI Extension tools for** the long tail and the compositional
cases:
- targets used rarely enough not to deserve a hotkey ("paste into Notes")
- "wherever I was just in" / "the app that was frontmost before Raycast"
- multi-step compositions ("clean with the technical-writing prompt
  and send to VS Code")
- anything where the target is genuinely variable per invocation

**Why both, not just AI Extensions:**

| Concern | Hotkey | AI Extension |
|---|---|---|
| Latency | sub-second | 1–3 s (AI routing round-trip) |
| Mid-dictation friction | none — fire and forget | high — requires opening Raycast AI and a second voice/text input loop on top of Voiceitt |
| Predictability | deterministic | depends on AI tool selection |
| Scales to N targets | one hotkey per target | one tool, infinite phrasings |

The shared `pasteIntoApp` implementation means adding a new target
becomes an entry in a per-app config map (bundle id, activation
strategy, default submit-key behavior), not "write another
`send-to-*.ts` file from scratch." Both pathways get the new target
for free as soon as it's in the map.

**Permission prompts (lesson 14) still apply per-target either way.**
The first time Raycast (via hotkey or via AI) tries to activate a
new app, macOS prompts. Make that visible in the new-target UX so
the user doesn't mistake the prompt for an error.

## How to use the salvage folder

Everything worth carrying forward is in [`salvage/`](./salvage/). The
[`salvage/README.md`](./salvage/README.md) is the index; start there.

**Specifically, do not paraphrase these files — copy them verbatim
and adapt:**

| Salvage file | Use it as |
|---|---|
| `salvage/prompts/default.md` | The new repo's first prompt, unchanged. |
| `salvage/snippets/cliclick-paste-ritual.md` | The reference any new `send-to-*` code must match byte-for-byte. |
| `salvage/scripts/send-to-vscode.sh` | The template for the default `cliclick-paste` strategy. |
| `salvage/scripts/send-to-iterm.sh` | The template when you need AppleScript-activate of a specific tab before pasting. |
| `salvage/scripts/open-voiceitt.sh` | The boot sequence (env file, Chrome window-raise, server detect-and-start). |
| `salvage/scripts/load-file-to-scratchpad.sh` | The pattern for any Raycast → server round-trip. |
| `salvage/bridge/serve.py` | The reference implementation of the four endpoints; port to FastAPI structure. |
| `salvage/bridge/script.js` | The Voiceitt-write detection, fail-open transform call, SSE listener, and faux-caret implementation. The faux-caret math in particular is fiddly; copy it. |
| `salvage/bridge/dictate.html` + `styles.css` | The two-pane layout, AI toggle, file strip, caret-visibility CSS. |
| `salvage/notes/LESSONS-LEARNED.md` | The 37-item list of "we already tried this." Re-read before any non-trivial decision. |

You may write a much smaller `voiceitt-transform` module in Python
(parking-lot 2026-05-20) but the request shape, prompt-loading logic,
`<TRANSCRIPT>` framing, and fail-mode handling in
`salvage/scripts/voiceitt-transform` are wisdom worth preserving.

---

## Open decisions for the user

These are not for the AI to decide unilaterally. Ask before committing:

1. **New repo name.** The prototype is `voiceitt-amp-bridge` (and was
   `voiceitt-iterm-bridge` before that — the README still uses the
   old name). The next-gen repo should drop the target-app suffix
   entirely; `voiceitt-bridge` is the obvious neutral choice.
> a: voiceitt-bridge
2. **Raycast: Script Commands now, Extension later — or Extension
   from day one?** The recommendation is "Script Commands now, flip
   when you need preferences UI." Confirm with the user before
   investing in the Node/TS pipeline. **If/when the flip happens,
   use `pnpm` v11+ with default `strictDepBuilds: true`, not `npm`**
   — see the "npm supply chain posture" section above.
> a: Script Commands now
3. **LLM provider posture.** Start Gemini-only and design for
   pluggable, or actually ship a second provider (Anthropic, OpenAI,
   local Ollama) in v0? The parking lot flagged "pluggable" as worth
   doing but did not commit to a second provider.
> a: Start Gemini-only and design for pluggable -- this is not part of MVP anyway
4. **Prompt picker design.** ROADMAP §1.2/§1.4 in the old repo
   sketched a picker + active-prompt sidecar. Does the user want a
   Raycast Extension preference UI, an in-page dropdown in the
   scratchpad header, or both?
> a: both, but the dropdown is the MVP
5. **Whether to migrate git history.** Probably no — the shape of
   the repo is different enough that a clean start is honest. The
   old repo stays as a reference (don't delete it).
> a: no

---

## What the user is doing while you read this

The user is *actively dictating* through the prototype to drive this
very session. That means:

- The prototype is **load-bearing** until the next-gen repo can
  replace it. Do not delete or refactor anything in the prototype
  unless the user asks.
- The prototype's `bridge/serve.py` is running on port 7531 right
  now. If you need to test the new repo's server, pick a different
  port (`7532` is fine) so you don't collide.
- The prototype's Raycast commands are bound to global hotkeys the
  user relies on. Don't change `~/.config/raycast/scripts/`
  symlinks or rename any `send-to-*.sh` until the user has hotkeys
  bound to the new equivalents.

When the next-gen repo is ready, the user will switch hotkeys over
manually and decommission the prototype themselves.
