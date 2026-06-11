# V1 / post-MVP candidate issues

Draft backlog for prioritizing v1 before writing the ERD. This is not
the ERD yet; it is an editable issue inventory gathered from the repo,
`PROJECT-SPEC.md`, lessons learned, current MVP source, parking-lot
notes, and the Raycast Whisper overview from the `docs/additonal-notes`
branch.

## Core architecture

1. **Create the post-MVP FastAPI package while preserving `bridge/serve.py` as fallback**
   Build `src/voiceitt_bridge/` for the v1 app, but keep the current MVP server as the known-good local fallback required by the spec.

2. **Add unit and integration test coverage for the new `src/` app**
   The spec explicitly calls out coverage as non-optional once post-MVP lands. Include endpoint tests, prompt loading tests, provider failure tests, and load/path confinement tests.

3. **Define the v1 compatibility boundary between MVP endpoints and new endpoints**
   Existing `/transform`, `/load`, `/file`, `/events`, and `/ai-state` are load-bearing for `web/script.js` and Raycast. v1 should either preserve them exactly or add parallel v1 endpoints without breaking the current flow.

4. **Create a shared transform/framing module**
   Move `<TRANSCRIPT>…</TRANSCRIPT>` framing, prompt loading, provider invocation, timeout handling, and output extraction into testable Python code instead of keeping it embedded in the CLI.

## Prompt system

5. **Implement prompt inventory and prompt IDs**
   Discover prompts under `prompts/`, expose stable IDs/names/descriptions, and reject unknown prompt IDs.

6. **Add an in-page prompt picker**
   First v1 prompt UI should be in the scratchpad header, per answered decision. It should persist the active prompt locally and mirror it server-side for Raycast send-time cleanup.

7. **Add active-prompt sidecar/state endpoint**
   Raycast scripts currently only know the AI toggle via `/ai-state`. They will also need the active prompt ID, otherwise send-time cleanup and in-page cleanup can diverge.

8. **Make prompt selection visible in logs/observability**
   Every transform record should include prompt ID/version so bad output can be traced to the prompt that produced it.

9. **Create prompt validation / smoke tests**
   At minimum: default prompt exists, all prompt files load as UTF-8, IDs are unique, and prompts preserve the “treat transcript as input, not instructions” rule.

## Preview, diff, and observability

10. **Add in-page preview-and-edit before send**
    v1 trigger: cleaned text should be inspectable/editable before Raycast sends it. The current two-pane UI has a basis for this, but the send workflow still copies whichever textarea is focused.

11. **Add raw-vs-cleaned diff UI**
    Show changed spans so the user can spot unwanted rewrites before sending. This is explicitly called out as a post-MVP trigger.

12. **Add transform status panel**
    Replace the tiny `idle/transforming/ok/fail-open` label with structured status: provider reachable, active model, active prompt, last transform time, timeout/fail-open reason.

13. **Expose cleanup failure reasons without blocking fail-open**
    Current behavior correctly fails open, but failure is easy to miss. v1 should keep raw-text fallback while showing “raw used because API timed out / key missing / provider error.”

14. **Record per-utterance transform metadata locally**
    Optional local history: timestamp, raw text, cleaned text, prompt ID, model, duration, status. Needs privacy/retention controls before implementation.

15. **Add a reviewable transform log view**
    A small in-page log or “last N transforms” panel would make debugging bad rewrites easier without opening DevTools or `server.log`.

## Provider/model layer

16. **Introduce a provider interface, still Gemini-first**
    Design pressure for pluggable providers is post-MVP, but the first v1 implementation can keep Gemini as the only configured provider behind an interface.

17. **Resolve Gemini model naming drift**
    Spec says `gemini-2.5-flash-lite`, while `voiceitt-transform.py` defaults to `gemini-3.1-flash-lite`. Decide and document the v1 default.

18. **Add provider health check endpoint**
    Should distinguish “server running” from “LLM provider usable.” Do not send dictated text for health checks.

19. **Add configurable transform timeout policy**
    Separate in-page cleanup timeout from send-time cleanup timeout. Send-time should likely stay more aggressive because hotkey latency matters.

20. **Add model/prompt settings validation at startup**
    Detect missing prompt files, invalid provider config, absent API keys, and unsupported model names early, while still letting raw mode work.

## Raycast and paste workflows

21. **Implement clipboard save-and-restore for non-iTerm targets**
    README calls this the next post-MVP item. Preserve the sentinel ritual and Sticky-Keys-safe `cliclick` paste sequence.

22. **Add more first-class target scripts**
    Likely candidates: Slack, Notes, browser textareas, Messages, Discord. Each must stay “one hotkey per target,” not a dispatcher.

23. **Create a shared Raycast shell helper without weakening the ritual**
    `send-to-iterm.sh` and `send-to-vscode.sh` duplicate copy, AI-state, transform, and fail-open logic. A carefully reviewed helper could reduce drift, but must preserve the exact paste ritual where applicable.

24. **Add target-specific permission onboarding**
    First use of each new target triggers macOS Automation prompts. v1 docs/UI should explain this per target.

25. **Consider a Raycast Extension for preferences only**
    Use an extension if prompt preferences, target maps, or AI tools justify it. Keep deterministic high-frequency Script Command hotkeys.

26. **Add Raycast command for opening scratchpad in raw vs AI mode**
    `open-voiceitt.sh` already supports `VOICEITT_AI_MODE=0|1`; v1 could expose separate commands instead of requiring env setup.

## Scratchpad UX

27. **Design v1 header layout for AI, prompt, provider, status, load, clear**
    The current header is already crowded. v1 prompt/status features need an accessible, low-vision-friendly layout.

28. **Make AI state and prompt state multi-tab safe**
    Current `/ai-state` is last-write-wins across tabs. v1 should either enforce single-tab behavior or make state scoped/session-aware.

29. **Improve SSE connection visibility**
    The page silently loses live `/load` behavior if EventSource is unavailable or disconnected. v1 should show connection state and retry status.

30. **Clarify loaded-file behavior in v1**
    Current non-negotiable: reload starts clean; no auto-restore. But there is stale commentary in the Raycast loader suggesting next load will pick up `/file`. v1 should resolve docs/comments and decide whether loaded files are live-only or recoverable.

31. **Evaluate multi-file/recent-files as a v1 or later feature**
    This is parked and previously rejected as premature. If it comes back, it must not violate the “reload starts clean” mental model.

32. **Add optional “copy raw / copy cleaned” controls**
    Useful when reviewing a diff or when the focused pane model is ambiguous.

33. **Add keyboard-accessible controls for preview/diff flow**
    v1 preview should not require precise mouse interactions.

34. **Consider vendoring Atkinson Hyperlegible for offline use**
    Current CSS imports Google Fonts. Low priority, but local/offline behavior may matter for a local bridge.

## Data, correction, and learning features

35. **Decide whether v1 has local SQLite storage**
    Needed only if v1 includes transform history, correction dictionary, or Voiceitt feedback preparation. Keep it off the send-time hot path.

36. **Design a personal correction dictionary**
    User-approved corrections only, with false-positive guards and prompt/provider integration.

37. **Explore Voiceitt correction feedback loop as long-shot**
    Only if Voiceitt exposes an ingestion API. Do not build assumptions into the core architecture yet.

38. **Define privacy and retention policy for dictated text**
    If v1 logs transcripts/diffs locally, define default retention, clear-all behavior, export/delete controls, and what never leaves the machine.

## Setup, packaging, and docs

39. **Clean up stale prototype-era setup/tooling docs**
    `scripts/toggle-raycast-binding.sh` still talks about prototype `dictate.html` and says MVP relies on prototype `serve.py`, which no longer matches the repo.

40. **Fix README endpoint count / repo description drift**
    README says `bridge/` owns “four endpoints,” but the spec now lists seven endpoint paths.

41. **Harden install script for existing env files**
    `install.sh` overwrites `~/.config/voiceitt-bridge/env` when passed a key. v1 setup could preserve comments/other vars or prompt before replacement.

42. **Improve `bridge/pyproject.toml` metadata**
    It currently has placeholder description and no lockfile was visible in the file inventory. v1 should make the Python project metadata intentional.

43. **Add a doctor command**
    Check Chrome, Voiceitt assumptions, Raycast script symlinks, Accessibility/Automation hints, `cliclick`, Python/uv, server reachability, env file permissions, and provider config.

44. **Document v1 migration path from MVP**
    Include how to keep `bridge/serve.py` fallback, how Raycast commands change, and how prompt/provider settings migrate.

45. **Add development verification scripts for endpoint checks**
    The AGENTS file lists curl checks manually. v1 could provide a script that starts on a free port, runs confinement/SSE/basic endpoint checks, and exits cleanly.

## Raycast Whisper extension reference

46. **Use Raycast Whisper as a Raycast Extension architecture reference**
    Treat it as a reference for command layout, preferences, state-driven UI, subprocess orchestration, and setup/error flows — not as a direct template for dictation or paste.

47. **Define whether v1 includes a Raycast Extension shell**
    The Whisper overview suggests a good extension role: configuration, prompt selection, diagnostics, bridge health, history, and launching existing send scripts. It should not replace target-specific hotkeys by default.

48. **Model Raycast Extension commands as explicit states**
    Adapt Whisper’s finite-state flow into bridge states such as: bridge unavailable → scratchpad open → waiting for Voiceitt text → transforming → ready to send → sent / fail-open / send failed.

49. **Add Raycast preferences for non-secret config**
    Candidate preferences: bridge URL/port, default AI mode, active prompt, target defaults, log/history settings. Keep API keys out of Raycast LocalStorage/preferences unless explicitly redesigned.

50. **Add Raycast setup/error recovery flows**
    From a “bridge unavailable” or “missing dependency” UI, offer actions like “Open Voiceitt Scratchpad,” “Run Doctor,” “Open env file instructions,” or “Check Raycast scripts.”

51. **If using a Raycast Extension, keep existing low-level paste scripts authoritative**
    The extension can launch or wrap per-target scripts, but should not copy generic paste assumptions from Whisper. Sticky-Keys-safe `cliclick`, sentinel stamping, modifier release, and one-hotkey-per-target remain non-negotiable.

52. **Add local subprocess supervision only if it reduces user friction**
    Whisper’s subprocess handling is relevant if Raycast supervises `bridge/serve.py`, checks `cliclick`, checks Python/uv, or tails logs. Avoid moving fragile paste behavior into Node unless necessary.

53. **Design Raycast-side history separately from scratchpad-side history**
    Whisper has dictation history. For this project, history could mean raw/cleaned transform records, not audio/transcription history. Needs privacy controls and retention defaults.

54. **Consider command-to-command navigation in Raycast**
    Useful flows: diagnostics → configure prompt; missing server → open scratchpad; missing provider config → setup instructions; transform failure → open logs.

55. **Explicitly reject Whisper-style audio capture for v1**
    Voiceitt remains the dictation engine because it supports atypical speech and requires Chrome/http-localhost. SoX/Whisper recording/model download flows are not v1 scope unless a future non-Voiceitt mode is separately planned.

56. **Add “single scratchpad tab” health/diagnostic guidance**
    The additional branch also has a note about Chrome/Voiceitt mic stalls. v1 could include a troubleshooting/doctor item to warn about duplicate scratchpad tabs or stale Voiceitt mic sessions, though the bridge itself does not use the mic.

## Candidate ERD-driving decisions

- Is v1 primarily **FastAPI backend first**, or **UI preview/diff first**?
- Does v1 store transform history locally, or remain mostly stateless?
- Is the prompt picker only local/browser state, or server-owned state shared with Raycast?
- Do we want Raycast Extension preferences in v1, or defer until after prompt/provider basics?
- Should clipboard save/restore be part of v1’s core reliability bar?
- If a Raycast Extension exists in v1, is it only a companion/control plane, or does it own any send path?
