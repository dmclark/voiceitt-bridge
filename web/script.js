const pad = document.getElementById('pad');
const padOut = document.getElementById('pad-out');
const clearBtn = document.getElementById('clear');
const statusEl = document.getElementById('status');
const aiToggle = document.getElementById('ai-toggle');
const fauxCaret = document.getElementById('faux-caret');

/*
 * ===========================================================
 *  AI master toggle (ERD §1.0)
 * ===========================================================
 *
 * Default-off opt-in for LLM post-processing. Inverts the §1.3
 * MVP behaviour (which auto-fired on every utterance) so the
 * baseline cost of dictating is zero LLM calls. Persisted to
 * localStorage so the choice survives reloads. ⌘↵ in the input
 * pane stays as a one-shot override that fires the transform
 * once regardless of the toggle state — useful for "try the
 * LLM on this one phrase without flipping the master switch".
 */
const AI_TOGGLE_KEY = 'voiceitt-bridge:ai-enabled';
// Optional URL override: ?ai=0 or ?ai=1 lets the dictate.sh /
// dictate-ai.sh Raycast wrappers force a specific mode at open time,
// regardless of what localStorage previously remembered. The override
// is also persisted so the next bare reload (no query) honors the
// new choice. Anything else leaves the persisted toggle alone.
const aiParam = new URLSearchParams(location.search).get('ai');
if (aiParam === '0' || aiParam === '1') {
  localStorage.setItem(AI_TOGGLE_KEY, aiParam);
}
let aiEnabled = localStorage.getItem(AI_TOGGLE_KEY) === '1';
aiToggle.checked = aiEnabled;

/*
 * Server-side mirror of the toggle, for the bash send-to-*.sh
 * scripts to curl. The bash side has no DOM access, so without this
 * the cleanup-at-send wiring in send-to-vscode.sh / send-to-iterm.sh
 * runs voiceitt-transform unconditionally — even when the user has
 * opted out via this toggle. Push on initial load (so the server
 * mirror matches localStorage from the very first hotkey) and on
 * every flip (toggle handler below). Fire-and-forget: errors are
 * logged but never block the page; bash side defaults to "0" / paste
 * raw on any curl failure, which matches the AI-off semantic anyway.
 */
function pushAiState() {
  fetch('/ai-state', {
    method: 'POST',
    headers: {'content-type': 'text/plain'},
    body: aiEnabled ? '1' : '0',
  }).catch((err) => console.warn('POST /ai-state failed', err));
}
pushAiState();

// Body class drives the CSS that hides #pane-out when AI is off.
// Kept as a body class (rather than inline style on #pane-out)
// so future visibility-coupled rules — e.g. dimming the status
// indicator, repositioning the faux caret — can hook the same flag.
function applyAiVisibility() {
  document.body.classList.toggle('ai-off', !aiEnabled);
}
applyAiVisibility();

// Default focus into the top (Dictated) pane so Voiceitt has somewhere
// to write. We do NOT force focus back to it on every click anymore
// (ERD §1.3 makes the bottom pane editable, so users need to be able
// to click into it).
//
// Window-level focus re-snaps to pad ONLY if no textarea currently
// has focus. That covers the "freshly-restored Chrome window" case
// (caret has been lost, restore it to the dictation pane) without
// stealing focus from `pad-out` when Raycast briefly takes OS focus
// to fire a send-to-* script. Without this guard, sending from the
// bottom pane would always copy the top pane instead.
function refocus() { pad.focus(); }
window.addEventListener('focus', () => {
  if (!(document.activeElement instanceof HTMLTextAreaElement)) {
    refocus();
  }
});
setTimeout(refocus, 0);

function clearAll() {
  pad.value = ''; padOut.value = '';
  lastInputSentToLLM = '';
  setStatus(aiEnabled ? 'idle' : 'off');
  // Drop the loaded-file strip too — Clear means "back to a blank
  // scratchpad", which includes forgetting the just-loaded filename.
  // Server-side state (in-memory _loaded slot) is intentionally NOT
  // touched: a fresh page load shouldn't resurrect cleared text, but
  // we also can't usefully PUT empty state from here without a new
  // endpoint, so we just clear the local view.
  hideLoadedStrip();
  refocus(); updateFauxCaret();
}
clearBtn.addEventListener('click', clearAll);

// Initial status reflects the persisted toggle state on first paint.
if (!aiEnabled) setStatus('off');

// Cmd+K to clear (works regardless of focused pane).
window.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    clearAll();
  }
});

/*
 * ===========================================================
 *  §1.3 — auto-trigger + manual ⌘↵ trigger
 * ===========================================================
 *
 * Auto-trigger: ROADMAP §1 "Trigger mechanics" established that
 * Voiceitt commits each utterance via `execCommand('insertHTML')`,
 * which fires:
 *   1. a synthetic (`isTrusted: false`) `paste` ClipboardEvent
 *   2. a trusted `input` event with `inputType: ''`
 * Real keystrokes / user paste don't have step 1. So we latch
 * `voiceittWriting = true` on the untrusted paste and consume it on
 * the very next `input` event. Manual edits to the input field do
 * not fire the auto-trigger — that's intentional (the whole point
 * of editing by hand is usually to fix a mis-recognition the model
 * would otherwise paper over). To re-run after a manual edit, use
 * the manual trigger (⌘↵).
 *
 * Manual trigger: ⌘↵ while the input pane is focused. Force-fires
 * the transform even if `inputField.value === lastInputSentToLLM`
 * (otherwise re-runs after manual tweaks would be no-ops).
 *
 * `lastInputSentToLLM` lets a future "↻ Re-run" button (ERD §1.2)
 * gate its disabled state without further plumbing.
 */
const TRANSFORM_DEBOUNCE_MS = 700;

let voiceittWriting = false;
let lastInputSentToLLM = '';
let debounceTimer = null;
let inFlight = null;

function setStatus(label, kind) {
  statusEl.textContent = label;
  statusEl.className = kind || '';
}

pad.addEventListener('paste', (e) => {
  if (!e.isTrusted) voiceittWriting = true;
}, true);

pad.addEventListener('input', () => {
  if (!voiceittWriting) return;
  voiceittWriting = false;
  // Hotfix: Voiceitt commits each utterance via
  // `execCommand('insertHTML')`, which does NOT trigger the native
  // "scroll caret into view" behaviour that real keystrokes get.
  // Once dictated text grows past the visible pane the insertion
  // point disappears off-screen, even though the textarea has
  // scrollbars. Re-pin the caret to the viewport on every Voiceitt
  // write so the user always sees where the next phrase will land.
  ensureCaretInView(pad);
  // Master toggle off: skip the LLM, just mirror the dictated text
  // into the bottom pane so the focus-driven send still works the
  // way the user expects ("send from whichever pane I'm in").
  if (!aiEnabled) {
    padOut.value = pad.value;
    setStatus('off');
    return;
  }
  scheduleTransform();
});

// Toggle handler: persist, and immediately reflect the new state.
// Disabling mid-call: abort any in-flight transform so the result
// doesn't land after the user opted out, then mirror the current
// input so the bottom pane is in a sensible state for the next send.
aiToggle.addEventListener('change', () => {
  aiEnabled = aiToggle.checked;
  localStorage.setItem(AI_TOGGLE_KEY, aiEnabled ? '1' : '0');
  pushAiState();
  if (!aiEnabled) {
    clearTimeout(debounceTimer);
    if (inFlight) { inFlight.abort(); inFlight = null; }
    padOut.value = pad.value;
    // Programmatic value assignment doesn't trigger native "scroll caret into view".
    // Ensure the caret stays visible if padOut has focus (though unlikely here
    // since we hide the pane immediately after).
    if (document.activeElement === padOut) ensureCaretInView(padOut);
    setStatus('off');
    // If pad-out had focus when the user disabled AI, the pane
    // about to be hidden was the active element — bounce focus
    // back to the still-visible input pane so the next dictation
    // (or hotkey send) lands on something sensible.
    if (document.activeElement === padOut) refocus();
  } else {
    // Don't fire retroactively on whatever's already in pad —
    // wait for the next utterance (or ⌘↵) so enabling the toggle
    // is never surprisingly expensive.
    setStatus('idle');
  }
  applyAiVisibility();
});

function scheduleTransform() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runTransform, TRANSFORM_DEBOUNCE_MS);
}

async function runTransform() {
  const text = pad.value;
  if (!text) { setStatus('idle'); return; }
  if (text === lastInputSentToLLM) return;
  lastInputSentToLLM = text;

  // Cancel any in-flight call so the freshest dictation always wins.
  if (inFlight) inFlight.abort();
  inFlight = new AbortController();

  setStatus('transforming…', 'busy');
  try {
    const r = await fetch('/transform', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({text}),
      signal: inFlight.signal,
    });
    if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + (await r.text()).slice(0, 200));
    const cleaned = await r.text();
    // Debug visibility — open DevTools (⌥⌘I) → Console to see each
    // round-trip. Cheap, removable, makes "is the LLM doing nothing
    // vs is it returning something different I can't tell apart"
    // distinguishable.
    console.log('[transform]', {input: text, output: cleaned, changed: cleaned !== text});
    padOut.value = cleaned;
    // Programmatic value assignment doesn't trigger native "scroll caret into view"
    // like user keystrokes do. Ensure the caret stays visible if padOut has focus.
    if (document.activeElement === padOut) ensureCaretInView(padOut);
    setStatus(cleaned === text ? 'ok (unchanged)' : 'ok', 'ok');
  } catch (err) {
    if (err.name === 'AbortError') return;
    // Fail-open: never block the user. Drop the raw text into the
    // output pane so the existing send-script flow still works,
    // and surface that we did so.
    console.warn('transform failed, falling back to raw text', err);
    padOut.value = text;
    // Programmatic value assignment doesn't trigger native "scroll caret into view"
    // like user keystrokes do. Ensure the caret stays visible if padOut has focus.
    if (document.activeElement === padOut) ensureCaretInView(padOut);
    setStatus('fail-open: raw', 'warn');
  } finally {
    inFlight = null;
    updateFauxCaret();
  }
}

// Manual trigger: ⌘↵ on the input field re-runs the transform,
// bypassing the lastInputSentToLLM gate (so post-edit re-runs
// actually go through). Gated on the master toggle: if AI is
// off, ⌘↵ is a no-op — "off means off", and firing the LLM into
// the hidden pad-out would be invisible work.
pad.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    if (!aiEnabled) return;
    clearTimeout(debounceTimer);
    lastInputSentToLLM = '';
    runTransform();
  }
});

/*
 * Faux-caret positioning (ROADMAP §0.5.4 step 5).
 *
 * Build a hidden <div> that mirrors the textarea's box + text up to
 * `selectionStart`, terminated by a zero-width <span>. The span's
 * client rect is the caret position; copy its top/left/height onto
 * the floating #faux-caret div.
 *
 * Relevant computed styles must match exactly or wrapping diverges
 * from the textarea and the caret lands on the wrong line.
 */
const MIRROR_PROPS = [
  'direction', 'boxSizing',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'borderStyle',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
  'fontSizeAdjust', 'lineHeight', 'fontFamily',
  'textAlign', 'textTransform', 'textIndent', 'textDecoration',
  'letterSpacing', 'wordSpacing', 'tabSize',
];

let mirror = null;
function getMirror() {
  if (mirror) return mirror;
  mirror = document.createElement('div');
  mirror.setAttribute('aria-hidden', 'true');
  Object.assign(mirror.style, {
    position: 'absolute',
    visibility: 'hidden',
    whiteSpace: 'pre-wrap',
    wordWrap: 'break-word',
    overflow: 'hidden',
    top: '0',
    left: '-9999px',
  });
  document.body.appendChild(mirror);
  return mirror;
}

/*
 * Scroll the textarea so its caret is inside the visible box.
 * Native textareas do this automatically on real keystrokes; they
 * do NOT do it for `execCommand('insertHTML')` (Voiceitt) or for
 * programmatic `value =` assignments. Reuses the faux-caret mirror
 * to compute the caret's Y offset inside the textarea content, then
 * nudges `scrollTop` only when the caret is outside the viewport
 * (so we don't yank the view around when it's already fine).
 */
function ensureCaretInView(ta) {
  if (!(ta instanceof HTMLTextAreaElement)) return;
  const m = getMirror();
  const cs = getComputedStyle(ta);
  for (const p of MIRROR_PROPS) m.style[p] = cs[p];
  m.style.width = ta.clientWidth + 'px';

  const pos = ta.selectionEnd;
  m.textContent = ta.value.substring(0, pos);
  const marker = document.createElement('span');
  marker.textContent = '\u200b';
  m.appendChild(marker);

  const mRect = m.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;
  const caretTop = markerRect.top - mRect.top;
  const caretBottom = caretTop + lineHeight;

  const viewTop = ta.scrollTop;
  const viewBottom = ta.scrollTop + ta.clientHeight;
  if (caretBottom > viewBottom) {
    ta.scrollTop = caretBottom - ta.clientHeight;
  } else if (caretTop < viewTop) {
    ta.scrollTop = caretTop;
  }
  updateFauxCaret();
}

function updateFauxCaret() {
  const ta = document.activeElement;
  if (!(ta instanceof HTMLTextAreaElement)) {
    fauxCaret.style.display = 'none';
    return;
  }
  const m = getMirror();
  const cs = getComputedStyle(ta);
  for (const p of MIRROR_PROPS) m.style[p] = cs[p];
  m.style.width = ta.clientWidth + 'px';

  const pos = ta.selectionStart;
  const before = ta.value.substring(0, pos);
  const after = ta.value.substring(pos) || '.';
  m.textContent = before;
  const marker = document.createElement('span');
  marker.textContent = '\u200b';
  m.appendChild(marker);
  m.appendChild(document.createTextNode(after));

  const taRect = ta.getBoundingClientRect();
  const mRect = m.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;

  fauxCaret.style.display = 'block';
  fauxCaret.style.left = (taRect.left + (markerRect.left - mRect.left) - ta.scrollLeft) + 'px';
  fauxCaret.style.top  = (taRect.top  + (markerRect.top  - mRect.top)  - ta.scrollTop)  + 'px';
  fauxCaret.style.height = lineHeight + 'px';

  // Restart blink so the caret is visible immediately after a move
  // (rather than possibly mid-blink-off).
  fauxCaret.style.animation = 'none';
  // eslint-disable-next-line no-unused-expressions
  fauxCaret.offsetHeight;
  fauxCaret.style.animation = '';
}

// Recompute on anything that can move the caret. Both panes are
// editable post-§1.3, so the faux caret tracks whichever one has
// focus (updateFauxCaret already keys off document.activeElement).
['input', 'click', 'keyup', 'focus', 'scroll', 'select'].forEach(evt => {
  pad.addEventListener(evt, updateFauxCaret);
  padOut.addEventListener(evt, updateFauxCaret);
});
function maybeHideFauxCaret() {
  // Defer so a focus change pad↔padOut doesn't briefly hide it.
  setTimeout(() => {
    if (!(document.activeElement instanceof HTMLTextAreaElement)) {
      fauxCaret.style.display = 'none';
    }
  }, 0);
}
pad.addEventListener('blur', maybeHideFauxCaret);
padOut.addEventListener('blur', maybeHideFauxCaret);
document.addEventListener('selectionchange', updateFauxCaret);
window.addEventListener('resize', updateFauxCaret);

// Track the focus font-size transition so the caret stays glued to
// the cursor across the 80 ms 22→26 px ease.
function trackTransition() {
  const start = performance.now();
  const tick = (now) => {
    updateFauxCaret();
    if (now - start < 140) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
pad.addEventListener('transitionrun', trackTransition);
padOut.addEventListener('transitionrun', trackTransition);

requestAnimationFrame(updateFauxCaret);

/*
 * ===========================================================
 *  Local-file loader (PARKING-LOT 2026-05-13 → graduated)
 * ===========================================================
 *
 * `scripts/load-file-to-scratchpad.sh` pops a macOS open-panel,
 * POSTs the chosen path to /load, and the server holds the file
 * contents in a single in-memory slot. This block:
 *
 *   - on page load, GETs /file once and populates the input pane
 *     if the slot is non-empty (so opening the scratchpad after
 *     the load still picks up the file);
 *   - keeps an EventSource open against /events; on `reload`
 *     re-fetches /file and swaps content live in the open tab.
 *
 * Direct `pad.value = ...` does NOT fire the auto-trigger
 * (voiceittWriting only latches on synthetic paste from Voiceitt's
 * insertHTML), so loading a file never costs an LLM call.
 */
const loadedStrip = document.getElementById('loaded-strip');
const loadedPath = document.getElementById('loaded-path');
const loadBtn = document.getElementById('load');
const filePicker = document.getElementById('file-picker');

// 50 KB / UTF-8 / hide-on-clear caps mirror the server's POST /load
// checks (see bridge/serve.py MAX_LOAD_BYTES). Browser path can't
// enforce $HOME containment — the OS open-panel already restricts
// what the user can pick, and there's no path leakage either way.
const MAX_LOAD_BYTES = 50 * 1024;

function showLoadedStrip(displayName, fullPath) {
  loadedPath.textContent = displayName;
  loadedStrip.title = fullPath || displayName;
  loadedStrip.classList.add('shown');
}
function hideLoadedStrip() {
  loadedStrip.classList.remove('shown');
  loadedPath.textContent = '';
  loadedStrip.title = '';
}

function applyLoadedFile(file) {
  if (!file || !file.path) {
    hideLoadedStrip();
    return;
  }
  // basename only — full path lives in the title attr if curiosity strikes.
  const base = file.path.split('/').pop() || file.path;
  showLoadedStrip(base, file.path);
  pad.value = file.text || '';
  // Mirror into pad-out so an immediate send-to-* (when AI is off,
  // pad-out is hidden but still the "outgoing" buffer in the AI-on
  // case) reflects the just-loaded text instead of stale dictation.
  padOut.value = pad.value;
  // Reset the LLM dedupe gate so a manual ⌘↵ after edits actually fires.
  lastInputSentToLLM = '';
  refocus();
  updateFauxCaret();
}

// Load… button → in-browser file picker. Reads via FileReader so
// we never need the absolute path (which the browser won't tell us
// anyway). For a server-side round-trip with a real path, use the
// Raycast 'Load File into Scratchpad' command.
loadBtn.addEventListener('click', () => filePicker.click());
filePicker.addEventListener('change', () => {
  const f = filePicker.files && filePicker.files[0];
  if (!f) return;
  if (f.size > MAX_LOAD_BYTES) {
    setStatus('too large', 'warn');
    filePicker.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    // FileReader.readAsText silently replaces invalid UTF-8 with U+FFFD;
    // detect that and refuse so the user isn't editing mojibake.
    const text = reader.result;
    if (typeof text !== 'string' || text.indexOf('\uFFFD') !== -1) {
      setStatus('not UTF-8', 'warn');
      filePicker.value = '';
      return;
    }
    showLoadedStrip(f.name, f.name);
    pad.value = text;
    padOut.value = text;
    lastInputSentToLLM = '';
    setStatus(aiEnabled ? 'idle' : 'off');
    refocus();
    updateFauxCaret();
    filePicker.value = '';  // allow re-picking the same file
  };
  reader.onerror = () => {
    setStatus('read failed', 'warn');
    filePicker.value = '';
  };
  reader.readAsText(f, 'utf-8');
});

async function fetchLoadedFile() {
  try {
    const r = await fetch('/file', {cache: 'no-store'});
    if (!r.ok) return;
    applyLoadedFile(await r.json());
  } catch (err) {
    console.warn('GET /file failed', err);
  }
}

// Deliberately NOT calling fetchLoadedFile() on initial page load.
// Page reload always starts clean (per the user's mental model: "a
// reload starts with a clean slate"). Server-side _loaded state may
// still be non-empty from a previous Raycast load, but it just sits
// there unused — only the live SSE `reload` path surfaces it. The
// Raycast loader assumes the scratchpad tab is already open.
//
// SSE: the server sends `event: reload` whenever /load succeeds.
// EventSource auto-reconnects with backoff, so we don't need our own
// retry loop — losing the connection just means the next /load won't
// live-swap until the browser reopens it.
try {
  const es = new EventSource('/events');
  es.addEventListener('reload', fetchLoadedFile);
} catch (err) {
  console.warn('EventSource unavailable; live reload disabled', err);
}
