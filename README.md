# voiceitt-bridge

Land Voiceitt-dictated text in arbitrary macOS apps — cleanly,
Sticky-Keys-safe, with an LLM polish step that fails open to the raw
transcript. Designed for one specific atypical-speech dictation
workflow; not a general-purpose dictation tool.

> **Status: Phase 0 scaffolding.** This repo is the next-gen successor
> to the `voiceitt-amp-bridge` prototype. The prototype is still
> load-bearing and running on `localhost:7531`; this repo is being
> built up alongside it and will replace it incrementally. See
> [HANDOFF.md](./HANDOFF.md) for the full vision and the Phase 0 / Phase 1
> split.

---

## What this repo contains today

```diagram
voiceitt-bridge/
├── README.md         ← you are here
├── HANDOFF.md        ← spec, non-negotiables, lessons pointers, open decisions
├── AGENTS.md         ← root routing doc for AI assistants
├── prompts/          ← LLM system prompts (cleanup, …)
├── web/              ← scratchpad page (vanilla HTML/CSS/JS, no build step)
├── raycast/          ← Raycast Script Commands + the cleanup transform
├── notes/            ← parking lot, design notes (empty in Phase 0)
├── scripts/          ← dev convenience (empty in Phase 0)
└── salvage/          ← verbatim artifacts from the prototype; reference only
```

`src/voiceitt_bridge/` (FastAPI app, prompt loader, framing module,
pluggable providers) and `tests/` arrive in Phase 1. Phase 0
deliberately ships **no Python**.

## The Phase 0 cleanup path

This repo's Phase 0 takes the **carry-`voiceitt-transform`-forward**
path (option (b) in HANDOFF.md §"Phase 0 first-PR scope"). Each
`send-to-*` Raycast hotkey:

```diagram
╭───────────────────╮  Cmd+A,Cmd+C  ╭────────────╮
│ Voiceitt          │──────────────▶│ Clipboard  │
│ scratchpad        │   (sentinel +  ╰─────┬──────╯
│ (raw dictation)   │    poll, l.10)       │ pbpaste
╰───────────────────╯                      ▼
                                  ╭──────────────────────╮
                                  │ voiceitt-transform   │
                                  │ (bash + curl + jq    │
                                  │  → Gemini, fail-open)│
                                  ╰──────┬───────────────╯
                                         │ cleaned text
                ╭────────────────────────┴───────────────────╮
                ▼                                            ▼
   ╭──────────────────────╮              ╭───────────────────────────╮
   │ iTerm                │              │ Other targets             │
   │ tell session to      │              │ pbcopy + cliclick Cmd+V   │
   │ write text … nl NO   │              │ (Sticky-Keys-safe ritual) │
   ╰──────────────────────╯              ╰───────────────────────────╯
```

The in-page AI toggle in `web/script.js` is carried forward unchanged
but stays **off by default** (non-negotiable 5); the send-time cleanup
above is the canonical Phase 0 cleanup path. When Phase 1 lands the
FastAPI `/transform` module and the in-page prompt-picker /
preview-and-edit UI, the in-page path will become canonical again.

## One-time setup

Phase 0 piggybacks on the prototype's runtime config dir
(`~/.config/voiceitt-bridge/`), the prototype's `serve.py` running on
port 7531, and the prototype's `~/.config/voiceitt-bridge/env` file
holding `GOOGLE_API_KEY`. The new `raycast/` scripts here are not yet
symlinked into Raycast — the prototype's are. **Do not switch hotkey
bindings to these scripts until the user explicitly chooses to flip.**

When you do flip:

1. `brew install cliclick` (Apple Silicon path
   `/opt/homebrew/bin/cliclick` is hard-coded in the scripts).
2. Ensure `~/.config/voiceitt-bridge/env` has `GOOGLE_API_KEY=…`.
3. Symlink `raycast/*.sh` and `raycast/voiceitt-transform` into your
   Raycast Script Commands directory.
4. **Grant Accessibility permission to Raycast** (per lesson 15;
   adding `cliclick` itself does nothing).
5. **Grant per-target Automation permission to Raycast** the first
   time each `send-to-*` script fires (per lesson 14; one OS prompt
   per target app).

## Clipboard hygiene (zero-code mitigation, do this first)

Every `send-to-*` hotkey under the clipboard ritual pollutes
clipboard-history tools. The smallest mitigation that pays off
immediately:

> **Raycast → Settings → Extensions → Clipboard History → Excluded
> Apps → add Raycast.**

This stops Raycast's own clipboard history from logging every
dictation transition. The iTerm `write text` strategy in
`raycast/send-to-iterm.sh` (the highest-volume destination) sidesteps
the clipboard entirely, further reducing pollution. The save-and-restore
wrapper for the remaining clipboard-using targets is deferred to a
later PR.

## Hotkeys (Phase 0)

| Script | Purpose | Paste strategy |
|---|---|---|
| `raycast/open-voiceitt.sh` | Open the scratchpad (raises existing Chrome window if found; else starts the prototype's `serve.py` and opens a new window) | — |
| `raycast/load-file-to-scratchpad.sh` | macOS open-panel → `POST /load` into the scratchpad | — |
| `raycast/send-to-iterm.sh` | Cleanup-at-send → iTerm `write text … newline NO` | bypasses clipboard |
| `raycast/send-to-vscode.sh` | Cleanup-at-send → VS Code via clipboard + cliclick Cmd+V | clipboard (transient) |

Other targets (Slack, Notes, browser textareas) are not yet wired in
Phase 0 — add by copying `raycast/send-to-vscode.sh`, changing
`TARGET_BUNDLE_ID`, and the `@raycast.title`. Each new target needs
its own Automation-permission prompt the first time it fires
(lesson 14).

## What is *not* in this PR

Explicitly out of scope (see [HANDOFF.md](./HANDOFF.md) for the full
list):

- FastAPI app, `src/voiceitt_bridge/`, `pyproject.toml`, `tests/`
- The `clipboard-restore` save-and-restore wrapper around the
  clipboard ritual (next PR)
- Any Raycast Extension work (Phase 1+, see HANDOFF "AI Extensions vs
  per-target hotkey commands")
- Prompt-picker UI (Phase 1+)
- Multi-provider LLM dispatch (Phase 1+; design-time only)

## Reference material

- [HANDOFF.md](./HANDOFF.md) — the spec, non-negotiables, and the
  Phase 0 / Phase 1 split.
- [salvage/README.md](./salvage/README.md) — index of verbatim
  artifacts carried over from the prototype.
- [salvage/notes/LESSONS-LEARNED.md](./salvage/notes/LESSONS-LEARNED.md)
  — 37 numbered "we already tried that" entries; referenced
  throughout `HANDOFF.md` and the per-directory `AGENTS.md` files.
- [salvage/snippets/cliclick-paste-ritual.md](./salvage/snippets/cliclick-paste-ritual.md)
  — the byte-for-byte source of truth for any new `send-to-*` paste
  step.
