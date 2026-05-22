# Parking lot

**[📖 README](../README.md)** · **[🗺 Roadmap](./ROADMAP.md)** · **[🧩 ERD](./ERD.md)** · **[🅿️ Parking lot](./PARKING-LOT.md)**

---

Unstructured ideas that are **not commitments**. Resist the urge to flesh
them out — the point is to dump and forget. When something graduates to
real work, move it into [ROADMAP.md](./ROADMAP.md) with a section number
and **delete** the line from here (don't archive).

Format: `- YYYY-MM-DD  one-line idea`. Group by theme.

## Targets

## Scratchpad

- 2026-05-05  log original dictation + corrected text (sqlite?) to potentially submit corrections back to Voiceitt for model training
- 2026-05-08  surface transform call status in a small box in the top-right of the output pane; maybe link to open server.log in a new window
- 2026-05-13  load a local file into the scratchpad to edit with Voiceitt, then push to target app
- 2026-05-13  scratchpad loader: support loading multiple files / recent-files dropdown
- 2026-05-15  voiceitt UI cannot float over arbitrary macOS apps — Chrome MV3 sandbox + Voiceitt's document.hasFocus() insertion gate kill DPiP / window-pinning / click-through paths; revisit only if forking the unpacked extension becomes acceptable

## Tooling / workflow
- 2026-05-20  Port voiceitt-transform from bash to Python — it's already 158 lines (most of it hand-rolled HTTP-status + jq error handling), shells out to python3 for realpath, and serve.py is already in the stack; ~50 lines of urllib.request would replace it cleanly. Reconsider when §1.5 multi-provider branching adds another fan-out.

## Misc
