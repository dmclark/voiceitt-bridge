# AGENTS.md — root routing

You are working on the **voiceitt-bridge** repo: the next-gen
successor to the `voiceitt-amp-bridge` prototype. Before making any
non-trivial change, read these in order:

1. [`HANDOFF.md`](./HANDOFF.md) — the spec, the MVP / post-MVP split,
   the non-negotiables, and the answered open decisions. Re-read the
   non-negotiables list before touching anything in `raycast/`,
   `web/`, or (when it exists) `src/`.
2. [`salvage/notes/LESSONS-LEARNED.md`](./salvage/notes/LESSONS-LEARNED.md)
   — 37 numbered entries. The non-negotiables in `HANDOFF.md` cite
   their lesson numbers; the *story* behind each constraint lives
   here.
3. The per-directory `AGENTS.md` for whichever area you're editing
   (`web/AGENTS.md`, `bridge/AGENTS.md`, `raycast/AGENTS.md`).

## Hard ground rules (these never bend)

- **Do not violate the non-negotiables in `HANDOFF.md`.** Every one is
  the result of a debugging session you didn't have to suffer through.
  If you think a non-negotiable should be revisited, surface it
  explicitly — don't quietly route around it.
- **MVP ≠ post-MVP.** *(Revised 2026-06-06 — the earlier "MVP ships
  no Python architecture" rule is withdrawn; see the dated
  decision-reversal note in `HANDOFF.md`.)* MVP **may** use Python
  freely: third-party dependencies are allowed — managed with
  **`uv`**, never bare `pip`, so a `pyproject.toml` + lockfile are
  legitimate MVP artifacts — and multi-file Python is fine.
  `bridge/serve.py` stays the MVP server (see
  [`bridge/AGENTS.md`](./bridge/AGENTS.md)); it is **not** replaced by
  FastAPI for MVP. What is still deferred to post-MVP is the
  *re-architecture*: the FastAPI app and the `src/voiceitt_bridge/`
  package layout (prompt-picker plumbing, pluggable providers, in-page
  preview/diff). If you find yourself reaching for FastAPI or building
  out `src/voiceitt_bridge/`, stop and check whether the request is
  actually post-MVP work.
- **Salvage is verbatim reference, not a mutable directory.** Read
  from `salvage/` freely; do not edit it.
- **Prune addressed/stale content from `notes/` and the docs.** When a
  parked idea graduates to real work or a statement is superseded,
  delete the line (`notes/PARKING-LOT.md` already says to). This does
  **not** apply to `salvage/` (stays verbatim) or to text explicitly
  marked *historical* / *superseded* (e.g. in `HANDOFF.md`), which is
  kept on purpose.
- **The prototype on `localhost:7531` is load-bearing.** The user is
  actively dictating through it. Do not change anything that could
  break it without asking.
- **Conventional Commits, topic branches, one logical change per
  commit, never push without asking.**

## Where things live

| Concern | Location |
|---|---|
| User-facing setup, daily flow, hotkey table | [`README.md`](./README.md) |
| Vision, non-negotiables, open decisions, MVP / post-MVP split | [`HANDOFF.md`](./HANDOFF.md) |
| LLM system prompts | [`prompts/`](./prompts/) |
| Scratchpad page (vanilla HTML/CSS/JS) | [`web/`](./web/) + [`web/AGENTS.md`](./web/AGENTS.md) |
| MVP HTTP server (stdlib `serve.py`) | [`bridge/`](./bridge/) + [`bridge/AGENTS.md`](./bridge/AGENTS.md) |
| Raycast Script Commands + MVP transform | [`raycast/`](./raycast/) + [`raycast/AGENTS.md`](./raycast/AGENTS.md) |
| Carried-over reference artifacts | [`salvage/`](./salvage/) |
| Parking lot, design notes (mostly post-MVP+) | [`notes/`](./notes/) |
| Dev convenience scripts (toggle, install) | [`scripts/`](./scripts/) |
| post-MVP FastAPI app + `src/voiceitt_bridge/` package, pluggable providers | *(does not exist yet; `bridge/serve.py` stays the MVP server)* |

## Verification expectations

- **Raycast / paste-ritual changes:** manually smoke-test with
  **System Settings → Accessibility → Keyboard → Sticky Keys ON**,
  end-to-end (dictate → cleanup → send-to-*). There is no automated
  substitute. See [`raycast/AGENTS.md`](./raycast/AGENTS.md).
- **`web/` changes:** open in Chrome with Voiceitt attached. Confirm
  the Voiceitt-write detection path (lesson 3) still triggers, the
  faux caret (lessons 4/27/28) still tracks, and AI-off remains the
  default (non-negotiable 5).
- **post-MVP (when it lands):** unit + integration tests on
  everything under `src/`; coverage is non-optional because the bash
  prototype had none and this is the moment to fix that.

## When in doubt

Ask the user. The "Open decisions for the user" section of
`HANDOFF.md` is short and was answered explicitly; for new decisions
of similar weight, surface them the same way before committing.
