# V1 ERD / architecture brief

Draft design brief distilled from [`v1-issues.md`](./v1-issues.md).
This is the bridge between the issue inventory and implementation. It
should stay small enough to answer: what state does v1 own, what can be
deferred, and what is the first safe implementation slice?

Development-process note: Mandrel is used as agent/project memory for
planning context, decisions, and handoffs. It is not part of the v1
runtime architecture; bridge-owned state still lives in the FastAPI app
and its local storage/API boundaries.

## V1 scope

### Now

- Create the post-MVP `src/voiceitt_bridge/` FastAPI package.
- Preserve `bridge/serve.py` as the known-good fallback.
- Keep existing MVP endpoint behavior compatible for the active
  scratchpad/Raycast workflow.
- Add test coverage for the new `src/` app from the start.
- Move transcript framing, prompt loading, provider invocation,
  timeout handling, and output extraction into shared testable code.
- Make prompt inventory and active prompt state backend-owned.
- Support preview/diff-led scratchpad work: raw text, cleaned text,
  transform status, failure reasons, and editable final text.
- Design local transform/correction storage, but keep it off the
  send-time hot path.
- Keep deterministic Raycast Script Commands authoritative for
  high-frequency sends.
- Design APIs so a future private Raycast Extension can act as a
  control-plane client.

### Later

- Raycast Extension shell and richer Raycast control-plane UI.
- Multi-file / recent-files scratchpad loading.
- SSE connection visibility beyond what is required for compatibility.
- Detailed v1 migration docs beyond script-level notes.
- Voiceitt correction submission/export adapter.
- Broader target catalog beyond the first post-MVP reliability work.

## Non-negotiable implementation constraints

- Dictation still enters through the Chrome scratchpad served from
  `http://localhost`.
- Existing send workflows must fail open to raw text.
- LLM cleanup must frame user text with `<TRANSCRIPT>…</TRANSCRIPT>`.
- Clipboard-based sends must preserve sentinel stamping and the
  Sticky-Keys-safe `cliclick` paste ritual.
- SQLite/history/correction storage must not be required for Raycast
  send success. If storage is locked, missing, corrupt, slow,
  migrating, or disabled, sending still proceeds and the storage
  failure is diagnostic-only.
- API keys stay in shell env / env files, not served browser code or
  Raycast preferences.

## Candidate domain entities

### Prompt

Represents a cleanup prompt available under `prompts/`.

- `id`
- `name`
- `description`
- `path`
- `version` or content hash
- `system_text`
- `created_at` / discovered timestamp

### ActivePromptState

Backend-owned current prompt selection shared by the scratchpad,
Raycast scripts, and a future Raycast Extension.

- `active_prompt_id`
- `updated_at`
- `updated_by` (`scratchpad`, `raycast-script`, `raycast-extension`,
  `server-default`)
- optional `session_id` if v1 chooses session-scoped state instead of
  global last-write-wins state

### TransformRequest

The input to cleanup. This can be an in-memory/request model before it
becomes a persisted record.

- `raw_text`
- `prompt_id`
- `provider_id`
- `model`
- `source` (`scratchpad`, `send-time`, `test`, etc.)
- `target_context_id` optional
- `requested_at`
- `timeout_ms`

### TransformRecord

Local observability record for one cleanup attempt.

- `id`
- `raw_text`
- `cleaned_text`
- `prompt_id`
- `prompt_version`
- `provider_id`
- `model`
- `duration_ms`
- `status` (`ok`, `fail_open`, `timeout`, `provider_error`,
  `disabled`, `empty_input`)
- `failure_reason`
- `source`
- `created_at`

### CorrectionLedgerEntry

Bridge-owned local record for future user-approved correction learning
or export. This must not mutate Voiceitt's internal Chrome-extension
SQLite database.

- `id`
- `transform_record_id` optional
- `raw_voiceitt_text`
- `ai_cleaned_text`
- `final_text`
- `correction_kind` (`recognition`, `style`, `rewrite`, `unknown`)
- `user_approved_for_training`
- `target_context_id` optional
- `submission_status` (`not_applicable`, `queued`, `exported`,
  `submitted`, `rejected`)
- `created_at`
- `updated_at`

### TargetContext

Optional metadata about where text is intended to go. This supports
observability and correction review without owning the send path.

- `id`
- `target_type` (`iterm`, `vscode`, `slack`, `browser`, `other`)
- `bundle_id` optional
- `command_name` optional
- `notes` optional

### ProviderConfig / ProviderStatus

Runtime configuration and health for cleanup providers. V1 can remain
Gemini-only behind this boundary.

- `provider_id`
- `model`
- `api_key_present` boolean only; never expose the key
- `configured`
- `last_checked_at`
- `last_status`
- `last_error`
- `default_timeout_ms`

### BridgeSetting

Small backend-owned settings that must be shared across clients.

- `key`
- `value`
- `updated_at`
- `updated_by`

Initial candidates: `ai_enabled`, `active_prompt_id`, default provider,
and retention settings.

## Relationship sketch

```text
Prompt 1 ── * TransformRecord
Prompt 1 ── 1 ActivePromptState

ProviderConfig 1 ── * TransformRecord
TargetContext 0..1 ── * TransformRecord

TransformRecord 0..1 ── * CorrectionLedgerEntry
TargetContext 0..1 ── * CorrectionLedgerEntry

BridgeSetting * ── backend-owned shared state
```

## API boundary sketch

These are design targets, not final route names.

- `GET /api/prompts` — list prompt inventory.
- `GET /api/prompt-state` — read active prompt.
- `PUT /api/prompt-state` — update active prompt.
- `POST /api/transforms` — run cleanup and return raw/cleaned/status
  metadata while preserving fail-open behavior at callers.
- `GET /api/transforms/recent` — optional local review/debug history.
- `GET /api/provider/status` — provider configuration and health
  without sending dictated text.
- `GET /api/health` — server health separate from provider health.
- `POST /api/corrections` — save an explicitly approved correction
  candidate, never on the required send path.

Compatibility decision: initial v1 FastAPI work should add parallel
`/api/*` routes only. Do not reimplement MVP-compatible `/transform`,
`/load`, `/file`, `/events`, or `/ai-state` in the first slice, and do
not modify the active `bridge/serve.py` or transform workflow in the
interim. Keep `bridge/serve.py` as the active compatibility server and
known-good fallback; revisit compatibility-route absorption only after
the new prompt/transform APIs and tests stabilize.

## First implementation slice

1. Create `src/voiceitt_bridge/` with FastAPI app factory and health
   endpoint.
2. Add pytest/httpx test harness for the new app.
3. Implement prompt inventory loading from `prompts/`.
4. Implement backend-owned active prompt state.
5. Extract transcript framing and prompt loading into shared code.
6. Add a transform service boundary with Gemini as the only provider
   initially, preserving fail-open behavior at callers.

Do not change Raycast send scripts or the active `bridge/serve.py`
workflow in this first slice unless compatibility tests require it.
