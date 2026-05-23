# AGENTS.md — `bridge/` conventions

The MVP HTTP server. A single Python 3 stdlib script (`serve.py`)
carried over verbatim from the prototype's `salvage/bridge/serve.py`.
Four endpoints, no framework, no third-party dependencies.

> Required reading before touching anything here:
> 1. [`../HANDOFF.md`](../HANDOFF.md) — particularly the "Endpoints
>    (carry over verbatim)" table, which is the contract this file
>    implements, and the MVP / post-MVP split blockquote, which
>    explains why this is a stdlib script and not a FastAPI app.
> 2. [`../salvage/notes/LESSONS-LEARNED.md`](../salvage/notes/LESSONS-LEARNED.md)
>    lessons 23, 24, 25 (SSE design, single-load-slot rule,
>    `$HOME`-confinement on `/load`).

## What this is — and what it deliberately is not

- **Is:** the MVP scratchpad server. Serves `web/` over `http://localhost`
  (which Voiceitt requires, per non-negotiable 2), shells out to the
  bash `voiceitt-transform` CLI for `POST /transform`, and runs the
  `/load` + `/file` + `/events` triplet that backs the
  `load-file-to-scratchpad.sh` Raycast command.
- **Is not:** the post-MVP `src/voiceitt_bridge/` FastAPI app. When
  prompt-picker, in-page preview-and-edit, diff UI, or pluggable LLM
  providers land, that work goes in `src/`, not here. This file
  stays the simple known-good fallback even after the FastAPI app
  ships — useful for bisection and for "just run the page locally"
  workflows.

## Conventions

- **Python 3 stdlib only.** No `pip install`. No `requirements.txt`.
  No virtualenv. If you find yourself wanting `httpx`, `pydantic`,
  `fastapi`, or anything else off PyPI, **stop**: that's the trigger
  to start post-MVP work in `src/voiceitt_bridge/`, not to add a
  dependency here.
- **One file.** `serve.py` is ~315 lines and stays one file. Multi-file
  refactors also point at post-MVP.
- **Carried verbatim from `salvage/bridge/serve.py`.** This file is
  byte-identical to its salvage source (`diff -q` returns clean).
  Internal docstring references to "ERD §x.y", "ROADMAP §1", and
  "PARKING-LOT 2026-05-13 → graduated" are prototype-era references;
  the equivalent context in this repo lives in `HANDOFF.md`,
  `salvage/notes/LESSONS-LEARNED.md`, and `salvage/notes/PARKING-LOT.md`.
  **Do not "clean up" those references** as a drive-by — keeping the
  verbatim-from-salvage property is more useful than tidying stale
  links.
- **Run via `python3 bridge/serve.py`.** No entry-point script, no
  `python -m`, no setuptools. The shebang is honored
  (`#!/usr/bin/env python3`) for direct execution.

## Configuration (all via env vars)

| Env var | Default | What this repo sets it to |
|---|---|---|
| `VOICEITT_BRIDGE_PORT` | `7531` | unchanged |
| `VOICEITT_BRIDGE_DIR` | `~/.config/voiceitt-bridge` | `<repo>/web` (set by `raycast/open-voiceitt.sh`) |
| `VOICEITT_TRANSFORM_CMD` | `$VOICEITT_BRIDGE_DIR/voiceitt-transform` | `<repo>/raycast/voiceitt-transform` (set by `raycast/open-voiceitt.sh`) |
| `VOICEITT_TRANSFORM_HARD_TIMEOUT` | `10` (seconds) | unchanged |

The defaults are wired for the prototype's directory layout (one
config dir holding everything). This repo overrides
`VOICEITT_BRIDGE_DIR` to point at `web/` so the server serves the
scratchpad page from the repo, and overrides `VOICEITT_TRANSFORM_CMD`
to point at `raycast/voiceitt-transform`. Both overrides are applied
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

Adding endpoints is fine for trivial reads. Changing the contract of
any existing endpoint requires a matching change in `web/script.js`
and any Raycast script that calls it (`load-file-to-scratchpad.sh`
hits `/load`).

## Things forbidden here

- **No third-party deps.** See the conventions above.
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
  VOICEITT_TRANSFORM_CMD="$PWD/raycast/voiceitt-transform" \
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
