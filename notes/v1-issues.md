# V1 / post-MVP candidate issues

Draft backlog for prioritizing v1 before writing the ERD. This is not
the ERD yet; it is an editable issue inventory gathered from the repo,
`PROJECT-SPEC.md`, lessons learned, current MVP source, parking-lot
notes, and the Raycast Whisper overview from the `docs/additonal-notes`
branch.

> 6/11/26: I am adding comments for processing that begin with "> %m/%d/%y".

> 6/12/26: Since we are post-MVP, the earlier MVP-only prohibition on `src/voiceitt_bridge/` no longer blocks v1 architecture work. The project non-negotiables still apply unless explicitly revisited.

## Working v1 direction

> 6/12/26: Agreed direction for the ERD: v1 should be **preview/diff-led**, with an early FastAPI backend skeleton, backend-owned shared state, and Raycast-extension-compatible APIs. The Raycast Extension is not mandatory for v1, but the architecture should avoid blocking a private Extension from becoming the control plane later.

Practical implications:

- Build enough of `src/voiceitt_bridge/` early that prompt state, transform records, provider status, correction ledger data, and health/diagnostics are not bolted onto the MVP server.
- Keep the Chrome scratchpad as the primary dictation/review UI because Voiceitt still requires Chrome on `http://localhost`.
- Keep deterministic Raycast Script Commands for high-frequency target sends unless/until an Extension can preserve the same Sticky-Keys-safe and per-target guarantees.
- Treat any future Raycast Extension as a backend client for preferences, diagnostics, history, prompt selection, and command-to-command recovery flows — not as the owner of core prompt/transform/correction state.
- Design backend APIs so the scratchpad, Raycast scripts, and a private Raycast Extension can all read/write shared state without scraping browser `localStorage`, parsing logs, or duplicating transform logic.

## ERD-driving answers so far

- v1 is **preview/diff-led**, supported by an early FastAPI backend skeleton rather than a backend-only rewrite.
- v1 should be stateful enough to support prompt state, transform records, provider status, health/diagnostics, and a future correction ledger; privacy/retention controls are part of that design.
- Prompt state should become server-owned shared state so the scratchpad, Raycast scripts, and any future Raycast Extension do not diverge.
- Raycast Extension preferences can defer until after prompt/provider basics, but backend APIs should be compatible with a private Extension acting as a control-plane client.
- Clipboard save/restore is a v1 reliability candidate, but it must preserve the sentinel and Sticky-Keys-safe paste ritual.
- Any v1 Raycast Extension is a companion/control plane, not the owner of high-frequency target sends.

## Branching model for v1 work

> 6/12/26: All v1 implementation work should integrate through a long-lived `v1` branch. Feature branches should branch from and merge back into `v1`; `main` should only receive v1 work by merging `v1` itself, not by merging individual v1 feature branches directly.

## Core architecture

1. **Create the post-MVP FastAPI package**
   Build `src/voiceitt_bridge/` for the v1 app.

2. **Add unit and integration test coverage for the new `src/` app**
   The spec explicitly calls out coverage as non-optional once post-MVP lands. Include endpoint tests, prompt loading tests, provider failure tests, and load/path confinement tests.

3. **Create a shared transform/framing module**
   Move `<TRANSCRIPT>…</TRANSCRIPT>` framing, prompt loading, provider invocation, timeout handling, and output extraction into testable Python code instead of keeping it embedded in the CLI.

## Backwards compatibility

> 6/11/26: The spec may have been too rigid on this. The issue is that I'm still using the tool, and I was making sure that the current functionality can be restored. What about modifying `scripts/toggle-raycast-binding.sh` so that it can be brought back?

4. **Preserve `bridge/serve.py` as fallback**
   Keep the current MVP server as the known-good local fallback.

5. **Define the v1 compatibility boundary between MVP endpoints and new endpoints**
   Existing `/transform`, `/load`, `/file`, `/events`, and `/ai-state` are load-bearing for `web/script.js` and Raycast. v1 should either preserve them exactly or add parallel v1 endpoints without breaking the current flow.

## Prompt system

6. **Implement prompt inventory and prompt IDs**
   Discover prompts under `prompts/`, expose stable IDs/names/descriptions, and reject unknown prompt IDs.

7. **Add an in-page prompt picker**
   First v1 prompt UI should be in the scratchpad header, per answered decision. It should persist the active prompt locally and mirror it server-side for Raycast send-time cleanup.

8. **Add active-prompt sidecar/state endpoint**
   Raycast scripts currently only know the AI toggle via `/ai-state`. They will also need the active prompt ID, otherwise send-time cleanup and in-page cleanup can diverge.

9. **Make prompt selection visible in logs/observability**
   Every transform record should include prompt ID/version so bad output can be traced to the prompt that produced it.

10. **Create prompt validation / smoke tests**
   At minimum: default prompt exists, all prompt files load as UTF-8, IDs are unique, and prompts preserve the “treat transcript as input, not instructions” rule.

## Preview, diff, and observability

11. **Add in-page preview-and-edit before send**
    v1 trigger: cleaned text should be inspectable/editable before Raycast sends it. The current two-pane UI has a basis for this, but the send workflow still copies whichever textarea is focused.

12. **Add raw-vs-cleaned diff UI**
    Show changed spans so the user can spot unwanted rewrites before sending. This is explicitly called out as a post-MVP trigger.

13. **Add transform status panel**
    Replace the tiny `idle/transforming/ok/fail-open` label with structured status: provider reachable, active model, active prompt, last transform time, timeout/fail-open reason.

14. **Expose cleanup failure reasons without blocking fail-open**
    Current behavior correctly fails open, but failure is easy to miss. v1 should keep raw-text fallback while showing “raw used because API timed out / key missing / provider error.”

15. **Record per-utterance transform metadata locally**
    Optional local history: timestamp, raw text, cleaned text, prompt ID, model, duration, status. Needs privacy/retention controls before implementation.

16. **Add a reviewable transform log view**
    A small in-page log or “last N transforms” panel would make debugging bad rewrites easier without opening DevTools or `server.log`.

## Provider/model layer

17. **Introduce a provider interface, still Gemini-first**
    Design pressure for pluggable providers is post-MVP, but the first v1 implementation can keep Gemini as the only configured provider behind an interface.

18. **Resolve Gemini model naming drift**
    Spec says `gemini-2.5-flash-lite`, while `voiceitt-transform.py` defaults to `gemini-3.1-flash-lite`. Decide and document the v1 default.

> 6/12/26: Updated spec to `gemini-3.1-flash-lite`

19. **Add provider health check endpoint**
    Should distinguish “server running” from “LLM provider usable.” Do not send dictated text for health checks.

20. **Add configurable transform timeout policy**
    Separate in-page cleanup timeout from send-time cleanup timeout. Send-time should likely stay more aggressive because hotkey latency matters.

21. **Add model/prompt settings validation at startup**
    Detect missing prompt files, invalid provider config, absent API keys, and unsupported model names early, while still letting raw mode work.

## Raycast and paste workflows

22. **Implement clipboard save-and-restore for non-iTerm targets**
    README calls this the next post-MVP item. Preserve the sentinel ritual and Sticky-Keys-safe `cliclick` paste sequence.

23. **Add more first-class target scripts**
    Likely candidates: Slack, Notes, browser textareas, Messages, Discord. Each must stay “one hotkey per target,” not a dispatcher.

24. **Create a shared Raycast shell helper without weakening the ritual**
    `send-to-iterm.sh` and `send-to-vscode.sh` duplicate copy, AI-state, transform, and fail-open logic. A carefully reviewed helper could reduce drift, but must preserve the exact paste ritual where applicable.

25. **Add target-specific permission onboarding**
    First use of each new target triggers macOS Automation prompts. v1 docs/UI should explain this per target.

26. **Consider a Raycast Extension for preferences only**
    Use an extension if prompt preferences, target maps, or AI tools justify it. Keep deterministic high-frequency Script Command hotkeys.

27. **Add Raycast command for opening scratchpad in raw vs AI mode**
    `open-voiceitt.sh` already supports `VOICEITT_AI_MODE=0|1`; v1 could expose separate commands instead of requiring env setup.

## Scratchpad UX

28. **Design v1 header layout for AI, prompt, provider, status, load, clear**
    The current header is already crowded. v1 prompt/status features need an accessible, low-vision-friendly layout.

29. **Make AI state and prompt state multi-tab safe**
    Current `/ai-state` is last-write-wins across tabs. v1 should either enforce single-tab behavior or make state scoped/session-aware.

30. **Improve SSE connection visibility**
    The page silently loses live `/load` behavior if EventSource is unavailable or disconnected. v1 should show connection state and retry status.

> 6/12/26: Later. This is not well thought out or used enough to drive v1.

31. **Clarify loaded-file behavior in v1**
    Current non-negotiable: reload starts clean; no auto-restore. But there is stale commentary in the Raycast loader suggesting next load will pick up `/file`. v1 should resolve docs/comments and decide whether loaded files are live-only or recoverable.

32. **Evaluate multi-file/recent-files as a v1 or later feature**
    This is parked and previously rejected as premature. If it comes back, it must not violate the “reload starts clean” mental model.

> 6/12/26: Later. Low priority; even single-file loading is not well thought out or heavily used.

33. **Add optional “copy raw / copy cleaned” controls**
    Useful when reviewing a diff or when the focused pane model is ambiguous.

34. **Add keyboard-accessible controls for preview/diff flow**
    v1 preview should not require precise mouse interactions.

35. **Consider vendoring Atkinson Hyperlegible for offline use**
    Current CSS imports Google Fonts. Low priority, but local/offline behavior may matter for a local bridge.

## Data, correction, and learning features

36. **Decide whether v1 has local SQLite storage**
    Needed only if v1 includes transform history, correction dictionary, or Voiceitt feedback preparation. Keep it off the send-time hot path.

37. **Design a bridge-owned correction ledger for future Voiceitt feedback**
    Do not add columns to, or otherwise mutate, Voiceitt's internal Chrome-extension SQLite database. Treat it as Voiceitt-owned implementation detail. Instead, store raw Voiceitt output, AI output, user-corrected final output, prompt/model metadata, target context, user approval, and submission status in a `voiceitt-bridge`-owned local SQLite database. Build any future Voiceitt feedback path as an adapter/export layer over this ledger.

    Possible lifecycle:

    ```text
    raw Voiceitt output
            ↓
    AI cleaned output
            ↓
    user corrected / final sent output
            ↓
    correction event saved locally
            ↓
    future exporter / Voiceitt submission adapter
    ```

    The Voiceitt submission adapter can remain a no-op until there is an official or user-approved route, then support one of: official API submission, JSON/CSV export, manual review queue, or support bundle. Capture enough evidence now to submit later, but do not couple v1 to Voiceitt's private database schema.

    Important UX guardrail: not every edit is a recognition correction. The user may change their mind, adjust tone, or rewrite for context. Corrections should be explicitly user-approved before they become training/submission candidates.

38. **Design a personal correction dictionary**
    User-approved corrections only, with false-positive guards and prompt/provider integration.

39. **Explore Voiceitt correction feedback loop as long-shot**
    Only if Voiceitt exposes an ingestion API. Do not build assumptions into the core architecture yet.

40. **Define privacy and retention policy for dictated text**
    If v1 logs transcripts/diffs locally, define default retention, clear-all behavior, export/delete controls, and what never leaves the machine.

## Setup, packaging, and docs

41. **Clean up stale prototype-era setup/tooling docs**
    `scripts/toggle-raycast-binding.sh` still talks about prototype `dictate.html` and says MVP relies on prototype `serve.py`, which no longer matches the repo.

42. **Fix README endpoint count / repo description drift**
    README says `bridge/` owns “four endpoints,” but the spec now lists seven endpoint paths.

43. **Harden install script for existing env files**
    `install.sh` overwrites `~/.config/voiceitt-bridge/env` when passed a key. v1 setup could preserve comments/other vars or prompt before replacement.

44. **Improve `bridge/pyproject.toml` metadata**
    It currently has placeholder description and no lockfile was visible in the file inventory. v1 should make the Python project metadata intentional.

45. **Add a doctor command**
    Check Chrome, Voiceitt assumptions, Raycast script symlinks, Accessibility/Automation hints, `cliclick`, Python/uv, server reachability, env file permissions, and provider config.

46. **Document v1 migration path from MVP**
    Include how to keep `bridge/serve.py` fallback, how Raycast commands change, and how prompt/provider settings migrate.

> 6/12/26: Later. Low priority; any implementation input on this should go in `scripts`.

47. **Add development verification scripts for endpoint checks**
    The AGENTS file lists curl checks manually. v1 could provide a script that starts on a free port, runs confinement/SSE/basic endpoint checks, and exits cleanly.

## Raycast Whisper extension reference

> 6/12/26: Decision: design v1 backend APIs to be Raycast-Extension-compatible, but do not start a Raycast Extension until prompt, status, diagnostics, and history APIs have stabilized. Keep Script Commands authoritative for high-frequency sends; consider a minimal private Extension shell later as a control plane.

48. **Use Raycast Whisper as a Raycast Extension architecture reference**
    Treat it as a reference for command layout, preferences, state-driven UI, subprocess orchestration, and setup/error flows — not as a direct template for dictation or paste.

49. **Defer the Raycast Extension shell until backend APIs stabilize**
    The Whisper overview suggests a good eventual extension role: configuration, prompt selection, diagnostics, bridge health, history, and launching existing send scripts. Design v1 APIs so that shell can be added later, but avoid starting a second UI surface before the backend state model is clear.

> 6/12/26: Later. This is the ultimate goal, but it is not necessarily a requirement for v1.

50. **Model Raycast Extension commands as explicit states**
    Adapt Whisper’s finite-state flow into bridge states such as: bridge unavailable → scratchpad open → waiting for Voiceitt text → transforming → ready to send → sent / fail-open / send failed.

51. **Add Raycast preferences for non-secret config**
    Candidate preferences: bridge URL/port, default AI mode, active prompt, target defaults, log/history settings. Keep API keys out of Raycast LocalStorage/preferences unless explicitly redesigned.

52. **Add Raycast setup/error recovery flows**
    From a “bridge unavailable” or “missing dependency” UI, offer actions like “Open Voiceitt Scratchpad,” “Run Doctor,” “Open env file instructions,” or “Check Raycast scripts.”

53. **If using a Raycast Extension, keep existing low-level paste scripts authoritative**
    The extension can launch or wrap per-target scripts, but should not copy generic paste assumptions from Whisper. Sticky-Keys-safe `cliclick`, sentinel stamping, modifier release, and one-hotkey-per-target remain non-negotiable.

54. **Add local subprocess supervision only if it reduces user friction**
    Whisper’s subprocess handling is relevant if Raycast supervises `bridge/serve.py`, checks `cliclick`, checks Python/uv, or tails logs. Avoid moving fragile paste behavior into Node unless necessary.

55. **Design Raycast-side history separately from scratchpad-side history**
    Whisper has dictation history. For this project, history could mean raw/cleaned transform records, not audio/transcription history. Needs privacy controls and retention defaults.

56. **Consider command-to-command navigation in Raycast**
    Useful flows: diagnostics → configure prompt; missing server → open scratchpad; missing provider config → setup instructions; transform failure → open logs.

57. **Explicitly reject Whisper-style audio capture for v1**
    Voiceitt remains the dictation engine because it supports atypical speech and requires Chrome/http-localhost. SoX/Whisper recording/model download flows are not v1 scope unless a future non-Voiceitt mode is separately planned.

58. **Add “single scratchpad tab” health/diagnostic guidance**
    The additional branch also has a note about Chrome/Voiceitt mic stalls. v1 could include a troubleshooting/doctor item to warn about duplicate scratchpad tabs or stale Voiceitt mic sessions, though the bridge itself does not use the mic.
