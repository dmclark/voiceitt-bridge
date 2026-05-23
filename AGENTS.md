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
   (`web/AGENTS.md`, `raycast/AGENTS.md`).

## Hard ground rules (these never bend)

- **Do not violate the non-negotiables in `HANDOFF.md`.** Every one is
  the result of a debugging session you didn't have to suffer through.
  If you think a non-negotiable should be revisited, surface it
  explicitly — don't quietly route around it.
- **MVP ≠ post-MVP.** MVP ships *no Python*. If you find
  yourself wanting to write FastAPI routes, a `pyproject.toml`, a
  `src/voiceitt_bridge/` package, or any tests under `tests/`, stop
  and check whether the request is actually post-MVP work.
- **Salvage is verbatim reference, not a mutable directory.** Read
  from `salvage/` freely; do not edit it.
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
| Raycast Script Commands + MVP transform | [`raycast/`](./raycast/) + [`raycast/AGENTS.md`](./raycast/AGENTS.md) |
| Carried-over reference artifacts | [`salvage/`](./salvage/) |
| Parking lot, design notes (mostly post-MVP+) | [`notes/`](./notes/) |
| Dev convenience scripts | [`scripts/`](./scripts/) |
| Python web app, providers, tests | *(post-MVP, does not exist yet)* |

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
