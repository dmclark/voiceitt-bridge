# AGENTS.md — `bridge/` conventions

The MVP HTTP server: `serve.py`, the prototype's `ThreadingHTTPServer`
carried over from `salvage/bridge/serve.py`. Four endpoints; it serves
the scratchpad and shells out to the cleanup transform.

> **Revised 2026-06-06:** the MVP/post-MVP reversal in `../HANDOFF.md`
> withdrew the stdlib-only constraint. This file is **no longer
> restricted to stdlib-only**. MVP Python may take third-party
> dependencies — managed with **`uv`**, never bare `pip` — and may
> span multiple files under `bridge/` where that buys something.
> Stdlib is still preferred when it suffices (don't add a dep you
> don't need), but reaching for one is no longer the trigger to jump
> to post-MVP. The one boundary that still holds: **`serve.py` stays
> the MVP server; it is not replaced by FastAPI for MVP.** The FastAPI
> + `src/voiceitt_bridge/` re-architecture remains post-MVP.

> Required reading before touching anything here:
> 1. [`../HANDOFF.md`](../HANDOFF.md) — particularly the "Endpoints
>    (carry over verbatim)" table, which is the contract this file
>    implements, and the revised MVP / post-MVP split blockquote, which
>    explains why this stays `serve.py` rather than a FastAPI app.
> 2. [`../salvage/notes/LESSONS-LEARNED.md`](../salvage/notes/LESSONS-LEARNED.md)
>    lessons 23, 24, 25 (SSE design, single-load-slot rule,
>    `$HOME`-confinement on `/load`).

## What this is — and what it deliberately is not

- **Is:** the MVP scratchpad server. Serves `web/` over `http://localhost`
  (which Voiceitt requires, per non-negotiable 2), shells out to the
  Python `voiceitt-transform.py` CLI for `POST /transform`, and runs the
  `/load` + `/file` + `/events` triplet that backs the
  `load-file-to-scratchpad.sh` Raycast command.
- **Is not:** the post-MVP `src/voiceitt_bridge/` FastAPI app. When
  prompt-picker, in-page preview-and-edit, diff UI, or pluggable LLM
  providers land, that work goes in `src/`, not here. This file
  stays the simple known-good fallback even after the FastAPI app
  ships — useful for bisection and for "just run the page locally"
  workflows.

## Conventions

- **Dependencies via `uv`, never bare `pip`.** Stdlib is still the
  default and preferred where it's enough; if you genuinely need a
  third-party package, add it with `uv` (`uv add …`) so it's captured
  in `pyproject.toml` + lockfile. The exception is `fastapi`/`uvicorn`
  specifically — wanting *those* means you're re-architecting, which
  belongs in `src/voiceitt_bridge/` (post-MVP), not here.
- **Multi-file is allowed.** `serve.py` may split into helper modules
  under `bridge/` if it earns its keep; there's no longer a one-file
  rule. Keep it as small as the job allows.
- **Carried (originally verbatim) from `salvage/bridge/serve.py`.**
  As of `fix/gate-cleanup-on-ai-toggle` the file is no longer
  byte-identical with its salvage source — the `/ai-state` endpoint
  was added so `raycast/send-to-*.sh` can gate cleanup-at-send on
  the page's AI master toggle (see commit message for the bug it
  fixes). Internal docstring references to "ERD §x.y", "ROADMAP §1",
  and "PARKING-LOT 2026-05-13 → graduated" are prototype-era
  references; the equivalent context in this repo lives in
  `HANDOFF.md`, `salvage/notes/LESSONS-LEARNED.md`, and
  `salvage/notes/PARKING-LOT.md`. **Do not "clean up" those
  references** as a drive-by — the carried-from-salvage origin is
  still useful context even now that the file has diverged.
- **Run via `python3 bridge/serve.py`** (or `uv run bridge/serve.py`
  once it has `uv`-managed deps). The shebang is honored
  (`#!/usr/bin/env python3`) for direct execution while it stays
  stdlib-only.

## Configuration (all via env vars)

| Env var | Default | What this repo sets it to |
|---|---|---|
| `VOICEITT_BRIDGE_PORT` | `7531` | unchanged |
| `VOICEITT_BRIDGE_DIR` | `~/.config/voiceitt-bridge` | `<repo>/web` (set by `raycast/open-voiceitt.sh`) |
| `VOICEITT_TRANSFORM_CMD` | `$VOICEITT_BRIDGE_DIR/voiceitt-transform.py` | `<repo>/bridge/voiceitt-transform.py` (set by `raycast/open-voiceitt.sh`) |
| `VOICEITT_TRANSFORM_HARD_TIMEOUT` | `10` (seconds) | unchanged |

The defaults are wired for the prototype's directory layout (one
config dir holding everything). This repo overrides
`VOICEITT_BRIDGE_DIR` to point at `web/` so the server serves the
scratchpad page from the repo, and overrides `VOICEITT_TRANSFORM_CMD`
to point at `bridge/voiceitt-transform.py`. Both overrides are applied
inside `raycast/open-voiceitt.sh` before launching the server, so a
user who just runs `python3 bridge/serve.py` by hand will get the
salvage defaults — fine for "I want to poke at it" but not the
intended path.

`GOOGLE_API_KEY` is consumed by `voiceitt-transform`, not by
`serve.py`. The server inherits whatever env is in scope when it's
launched; `raycast/open-voiceitt.sh` sources
`~/.config/voiceitt-bridge/env` before exec'ing the server so the
key lands in scope (see [`../README.md`](../README.md) "GOOGLE_API_KEY"
for the full provisioning story).

## Endpoints (contract; do not change without updating `web/script.js`)

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| `GET` | `/` and any static path under `$VOICEITT_BRIDGE_DIR` | — | static file | `SimpleHTTPRequestHandler` default; serves `index.html` for `/`. |
| `POST` | `/transform` | `{"text": "..."}` | `text/plain` (cleaned) on 200; 5xx on transform failure | Shells out to `voiceitt-transform`; 502 surfaces the last stderr line. The page is **expected to fail open** on any non-2xx (non-negotiable 4). |
| `POST` | `/load` | `{"path": "<abs or ~-relative>"}` | `text/plain "ok"` on 200; 4xx with one-line reason otherwise | Hard caps: ≤50 KB, UTF-8, path must resolve under `$HOME` (non-negotiable 9, lesson 25). |
| `GET` | `/file` | — | `application/json {"path":"...","text":"..."}` | Returns the single in-memory load slot; `{"path":"","text":""}` when nothing is loaded. |
| `GET` | `/events` | — | `text/event-stream` | SSE; emits `event: reload` whenever `/load` succeeds, plus a 15-second `: ping` heartbeat comment. |
| `GET` | `/ai-state` | — | `text/plain "0"` or `"1"` | Reports the page's last-pushed AI master-toggle state. Defaults to `"0"` on server start. `raycast/send-to-*.sh` curls this to decide whether to run cleanup-at-send. |
| `POST` | `/ai-state` | `text/plain "0"` or `"1"` (raw body, not JSON) | `text/plain "ok"` on 200; 400 with one-line reason otherwise | Page calls this on initial load and on every toggle flip so the server mirror stays in sync with `localStorage`. |

Adding endpoints is fine for trivial reads. Changing the contract of
any existing endpoint requires a matching change in `web/script.js`
and any Raycast script that calls it (`load-file-to-scratchpad.sh`
hits `/load`).

## Things forbidden here

- **No bare `pip` / unmanaged deps.** Use `uv` so any dependency is
  captured in `pyproject.toml` + lockfile; don't `pip install` into a
  loose environment. And don't pull `fastapi`/`uvicorn` in here —
  that's the post-MVP re-architecture trigger (see conventions).
- **No multi-file load slot, no recent-files history.** The single
  in-memory `_loaded` slot is intentional (lesson 24); auto-restore
  on reload is intentionally absent.
- **No `POST /load` outside `$HOME`.** The realpath-under-$HOME guard
  is load-bearing (lesson 25). Don't relax it.
- **No API keys in code or in the served page.** `GOOGLE_API_KEY`
  belongs in the shell env / env file consumed by
  `voiceitt-transform` (non-negotiable 8, lesson 18).

## Verification

```bash
# Boot on a free port so we don't fight the prototype on :7531.
VOICEITT_BRIDGE_PORT=7532 \
  VOICEITT_BRIDGE_DIR="$PWD/web" \
  VOICEITT_TRANSFORM_CMD="$PWD/bridge/voiceitt-transform.py" \
  python3 bridge/serve.py &

# Static serve
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7532/index.html
# expect: 200

# /transform pass-through (empty input)
curl -s -X POST -H 'content-type: application/json' \
  --data '{}' http://127.0.0.1:7532/transform
# expect: empty body, 200

# /load guard ($HOME-confinement)
curl -s -X POST -H 'content-type: application/json' \
  --data '{"path":"/etc/hosts"}' http://127.0.0.1:7532/load
# expect: 403 "path resolves outside $HOME"

# SSE liveness (will hang; Ctrl-C to abort)
curl -N http://127.0.0.1:7532/events
# expect: ": connected" immediately, ": ping" every 15s
```

End-to-end with the scratchpad page open and Voiceitt attached is the
only test that exercises the round-trip (and there's no automated
substitute for the Voiceitt-write-detection path; see
[`../web/AGENTS.md`](../web/AGENTS.md)).
