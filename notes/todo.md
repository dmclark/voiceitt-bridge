# MVP Completion Todo List

MVP is complete as of 2026-06-10. End-to-end validation has been
completed, and low latency has not been an issue in practice. Remaining
status/observability work is deferred to the next ERD for post-MVP / v1.

## 1. Core Infrastructure & Tooling
- [x] **Standardized Project Structure**: Migrate from `voiceitt-amp-bridge` structure to a clean, decoupled repository (`voiceitt-bridge`).
- [x] **Dependency Management**: Transition to `uv` for Python management with a proper `pyproject.toml` and lockfile (no bare `pip` installs).
- [x] **Static Prompt File**: Ensure `prompts/default.md` exists and is consumed by `voiceitt-transform` (single prompt, no switching). *Prompt management/switching and the prompt-picker are post-MVP — see the Post-MVP section below.*

## 2. The Bridge (MVP Backend)
- [x] **Core API Endpoints** (in `bridge/serve.py`; no `/transcribe` — Voiceitt transcribes in-browser, the bridge never handles audio):
    - `GET /` (+ static): serve the scratchpad page from `web/`.
    - `POST /transform`: process text via LLM (wrap in `<TRANSCRIPT>`, fail-open on failure).
    - `POST /load` + `GET /file`: load a local file (≤50 KB, UTF-8, under `$HOME`) into the scratchpad slot and read it back.
    - `GET /events`: SSE stream (emits `reload` on `/load`, 15s heartbeat).
    - `GET` / `POST /ai-state`: mirror the page's AI master-toggle so `send-to-*` can gate cleanup-at-send.
- [x] **Robust Transformation Logic**: 
    - Implement "fail-open" mode (return raw transcript on LLM failure).
    - Ensure strict handling of LLM output formatting to remove conversational filler.

## 3. The Scratchpad (Frontend)
- [x] **Two-Pane Layout**: Develop the UI for viewing/editing transcription content vs. system status/configuration.
- [x] **Voiceitt-Write Detection**: Implement logic to detect when user accepts transcription into buffer (Lesson 3).
- [x] **Faux Caret System**: Implement the visual indicator (caret) that tracks the cursor during transition from transcription to output.
- [x] **AI-Off Toggle**: Mandatory "non-negotiable" feature to bypass LLM and provide raw transcripts.

## 4. Raycast Integration (The Glue)
- [x] **Script Commands**: Implement a suite of `send-to-*` scripts using `cliclick` for clipboard handoff.
- [x] **Clipboard Rituals**: Implement the "Paste Ritual" to ensure text is correctly placed in target apps after commands are triggered.
- [x] **Context-Aware Commands**: Raycast commands that distinguish between raw and transformed versions based on state.

## 5. Non-Negotiable MVP Requirements (from PROJECT-SPEC.md)
- [x] **Zero Breaking Changes**: Ensure transition maintains all core functionality of the prototype.
- [x] **Standardized Fallbacks**: Always return a transcript if transformation fails.
- [x] **Low Latency**: End-to-end validation completed; bridge overhead has not been an issue in practice.

## Post-MVP (deferred — NOT part of MVP completion)
- [ ] **Real-time Connection Status / Observability**: Visual indicators for bridge connection, LLM/provider availability, and richer transform status. To be designed in the next ERD for post-MVP / v1 rather than patched into the MVP server.
- [ ] **Prompt Management**: System for organizing/isolating multiple system prompts beyond the single `prompts/default.md`.
- [ ] **Portability / Prompt-Picker Logic**: In-page dropdown in the scratchpad header (and later a Raycast preference UI) to switch cleanup prompts without hardcoding. (`PROJECT-SPEC.md` post-MVP trigger; README "What's Not in This MVP".)
- [ ] **Prompt Loading Engine**: Selection-ID-keyed loader to fetch the correct prompt from `prompts/` — depends on the picker above.

## Summary Checklist for Completion
- [x] **Infrastructure:** `uv` setup + `pyproject.toml` + `/prompts/` folder.
- [x] **Backend:** `bridge/serve.py` updated with robust transformation (fail-open). *(Selection-ID prompt loading is post-MVP.)*
- [x] **Frontend:** `web/` contains 2-pane UI, "AI-off" toggle, and "Faux Caret".
- [x] **Integration:** Raycast scripts implemented with standard `cliclick` paste ritual.
- [x] **Validation:** Successful end-to-end test (Dictate $\rightarrow$ Cleanup $\rightarrow$ Send) via a Raycast hotkey.
