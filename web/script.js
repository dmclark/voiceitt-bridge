const pad = document.getElementById('pad');
const padOut = document.getElementById('pad-out');
const clearBtn = document.getElementById('clear');
const statusEl = document.getElementById('status');
const aiToggle = document.getElementById('ai-toggle');
const promptPicker = document.getElementById('prompt-picker');
const promptManagerToggle = document.getElementById('prompt-manager-toggle');
const promptManager = document.getElementById('prompt-manager');
const promptManagerList = document.getElementById('prompt-manager-list');
const promptNewBtn = document.getElementById('prompt-new');
const promptSetActiveBtn = document.getElementById('prompt-set-active');
const promptArchiveBtn = document.getElementById('prompt-archive');
const promptManagerStatus = document.getElementById('prompt-manager-status');
const promptIdInput = document.getElementById('prompt-id');
const promptEditor = document.getElementById('prompt-editor');
const promptValidateBtn = document.getElementById('prompt-validate');
const promptSaveBtn = document.getElementById('prompt-save');
const promptValidation = document.getElementById('prompt-validation');
const previewStatus = document.getElementById('preview-status');
const apiHealthStatus = document.getElementById('api-health-status');
const apiPromptsLink = document.getElementById('api-prompts-link');
const apiDocsLink = document.getElementById('api-docs-link');
const fauxCaret = document.getElementById('faux-caret');

/*
 * ===========================================================
 *  AI master toggle
 * ===========================================================
 *
 * Default-off opt-in for LLM post-processing, so the baseline cost of
 * dictating is zero LLM calls. Persisted to
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
// because the editable bottom pane must keep focus when selected.
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
window.addEventListener('blur', () => {
  // Raycast send hotkeys move focus out of Chrome. The textarea can
  // otherwise remain `document.activeElement` in the background tab,
  // which leaves Voiceitt's visual recording affordance looking active
  // after the mic has audibly stopped. Explicitly blur on window loss;
  // the focus handler above re-arms the dictation pane when Chrome is
  // brought back.
  if (document.activeElement instanceof HTMLTextAreaElement) {
    document.activeElement.blur();
  }
});
setTimeout(refocus, 0);

function clearAll() {
  pad.value = ''; padOut.value = '';
  lastInputSentToLLM = '';
  setPreviewStatus('');
  setStatus(aiEnabled ? 'idle' : 'off');
  pushScratchpadState('empty');
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
 *  Auto-trigger + manual ⌘↵ trigger
 * ===========================================================
 *
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
 * `lastInputSentToLLM` also prevents duplicate transform calls.
 */
const TRANSFORM_DEBOUNCE_MS = 700;

let voiceittWriting = false;
let lastInputSentToLLM = '';
let debounceTimer = null;
let inFlight = null;
let transformRunId = 0;
let activePromptId = '';
let apiBase = '';
let apiAvailable = false;
let promptInventory = [];
let editingPromptId = '';
let creatingPrompt = false;

function setStatus(label, kind) {
  statusEl.textContent = label;
  statusEl.className = kind || '';
}

function setPreviewStatus(label) {
  previewStatus.textContent = label ? '— ' + label : '';
}

/*
 * ===========================================================
 *  Preview API client
 * ===========================================================
 *
 * The browser-visible API base is selectable with
 * `?api=http://localhost:7532/api`, allowing independently configured
 * local instances. Transform calls never fall back to an alternate
 * endpoint: if the API is unavailable, the page fails open to raw text
 * so the missing dependency remains visible.
 */
const API_BASE_STORAGE_KEY = 'voiceitt.apiBase';
const API_DEFAULT_BASE_CANDIDATES = [
  '/api',
  'http://127.0.0.1:7532/api',
  'http://localhost:7532/api',
];
const API_BASE_CANDIDATES = configuredApiBaseCandidates();
const API_FETCH_TIMEOUT_MS = 1200;
const API_HEALTH_POLL_MS = 5000;
let apiDiscoveryInFlight = false;
let apiHealthTimer = null;

function configuredApiBaseCandidates() {
  const configuredBase = configuredApiBase();
  const candidates = configuredBase ? [configuredBase] : API_DEFAULT_BASE_CANDIDATES;
  return candidates.filter((apiBase, index) => candidates.indexOf(apiBase) === index);
}

function configuredApiBase() {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('api');
  if (fromUrl !== null) {
    const normalized = normalizeApiBase(fromUrl);
    if (normalized) localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
    else localStorage.removeItem(API_BASE_STORAGE_KEY);
    return normalized;
  }
  return normalizeApiBase(localStorage.getItem(API_BASE_STORAGE_KEY) || '');
}

function normalizeApiBase(apiBase) {
  const trimmed = apiBase.trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  return trimmed.endsWith('/api') ? trimmed : trimmed + '/api';
}

async function fetchApiJson(resource, options) {
  return fetchJsonFromApiBase(apiBase, resource, options);
}

function fetchApi(resource, options) {
  return fetch(apiBase + resource, options);
}

async function fetchJsonFromApiBase(apiBase, resource, options) {
  const controller = options && options.signal ? null : new AbortController();
  const timeout = controller
    ? setTimeout(() => controller.abort(), API_FETCH_TIMEOUT_MS)
    : null;

  try {
    const response = await fetch(apiBase + resource, {
      cache: 'no-store',
      ...(options || {}),
      signal: controller ? controller.signal : options.signal,
      headers: {
        ...(options && options.headers ? options.headers : {}),
      },
    });
    if (!response.ok) throw new Error(apiBase + resource + ' HTTP ' + response.status);
    return response.json();
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

async function fetchHealthFromApiBase(apiBase) {
  return fetchJsonFromApiBase(apiBase, '/health');
}

async function fetchApiHealth() {
  if (!apiBase) throw new Error('no API base discovered');
  return fetchHealthFromApiBase(apiBase);
}

async function refreshApiHealth() {
  if (!apiBase) {
    initApi();
    return;
  }

  try {
    setApiHealthStatus(await fetchApiHealth());
  } catch (err) {
    console.info(apiBase + ' health unavailable', err);
    apiBase = '';
    apiAvailable = false;
    promptPicker.disabled = true;
    renderPromptManagerList();
    setApiHealthStatus({status: 'offline'});
  }
}

function startApiHealthPolling() {
  if (apiHealthTimer) return;
  apiHealthTimer = setInterval(refreshApiHealth, API_HEALTH_POLL_MS);
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForApiDiscovery() {
  const started = performance.now();
  while (apiDiscoveryInFlight && performance.now() - started < API_FETCH_TIMEOUT_MS * API_BASE_CANDIDATES.length) {
    await delay(50);
  }
}

async function ensureApiAvailable() {
  if (!apiAvailable && !apiDiscoveryInFlight) initApi();
  if (!apiAvailable && apiDiscoveryInFlight) await waitForApiDiscovery();
  if (!apiAvailable) throw new Error('API unavailable');
}

function renderPromptPicker(prompts, state) {
  promptInventory = prompts;
  promptPicker.innerHTML = '';
  for (const prompt of prompts) {
    const option = document.createElement('option');
    option.value = prompt.id;
    option.textContent = prompt.name || prompt.id;
    option.title = prompt.path || prompt.id;
    promptPicker.appendChild(option);
  }
  activePromptId = state.active_prompt_id || (prompts[0] && prompts[0].id) || '';
  promptPicker.value = activePromptId;
  promptPicker.disabled = prompts.length === 0;
  renderPromptManagerList();
}

/*
 * ===========================================================
 *  Prompt management UI
 * ===========================================================
 *
 * The top-bar picker is intentionally tiny because it is in the daily
 * dictation path. The manager below is an explicit, collapsible control
 * plane for API-backed authoring actions: list,
 * read full text, validate, save, archive, and set active. It is still
 * local-only browser JS; prompt writes stay server-side so the page never
 * learns secrets or writes files directly.
 */
function setPromptManagerStatus(label, kind) {
  promptManagerStatus.textContent = label;
  promptManagerStatus.className = kind || '';
}

function setPromptValidation(messages, kind) {
  const items = Array.isArray(messages) ? messages : [messages];
  promptValidation.textContent = items.filter(Boolean).join('; ');
  promptValidation.className = kind || '';
}

function selectedManagerPromptId() {
  return promptManagerList.value || editingPromptId || activePromptId;
}

function promptExists(promptId) {
  return promptInventory.some(prompt => prompt.id === promptId);
}

function renderPromptManagerList() {
  promptManagerList.innerHTML = '';
  for (const prompt of promptInventory) {
    const option = document.createElement('option');
    option.value = prompt.id;
    option.textContent = prompt.id === activePromptId ? prompt.id + ' (active)' : prompt.id;
    option.title = prompt.path || prompt.id;
    promptManagerList.appendChild(option);
  }

  const hasPrompts = promptInventory.length > 0;
  if (creatingPrompt) promptManagerList.selectedIndex = -1;
  promptManagerList.disabled = !hasPrompts;
  promptSetActiveBtn.disabled = !apiAvailable || creatingPrompt || !hasPrompts || selectedManagerPromptId() === activePromptId;
  promptArchiveBtn.disabled = !apiAvailable || creatingPrompt || !hasPrompts;
  promptValidateBtn.disabled = !apiAvailable;
  promptSaveBtn.disabled = !apiAvailable;
  if (!creatingPrompt && editingPromptId && promptExists(editingPromptId)) promptManagerList.value = editingPromptId;
}

async function refreshPromptsForUi(selectPromptId) {
  await ensureApiAvailable();
  const prompts = await fetchApiJson('/prompts');
  const state = await fetchApiJson('/prompt-state');
  renderPromptPicker(prompts, state);
  if (selectPromptId && promptExists(selectPromptId)) {
    promptManagerList.value = selectPromptId;
    await loadPromptIntoEditor(selectPromptId);
  }
}

async function loadPromptIntoEditor(promptId) {
  if (!promptId) return;
  setPromptValidation('');
  setPromptManagerStatus('loading…');
  const prompt = await fetchApiJson('/prompts/' + encodeURIComponent(promptId));
  creatingPrompt = false;
  editingPromptId = prompt.id;
  promptIdInput.value = prompt.id;
  promptEditor.value = prompt.system_text || '';
  renderPromptManagerList();
  setPromptManagerStatus(prompt.id === activePromptId ? 'loaded active prompt' : 'loaded', 'ok');
}

function startNewPrompt() {
  creatingPrompt = true;
  editingPromptId = '';
  promptManagerList.value = '';
  promptIdInput.value = '';
  promptEditor.value = '';
  setPromptManagerStatus('new prompt');
  setPromptValidation('');
  promptIdInput.focus();
  renderPromptManagerList();
}

async function validatePromptEditor() {
  await ensureApiAvailable();
  const promptId = promptIdInput.value.trim();
  if (!promptId) {
    setPromptValidation('prompt id is required', 'warn');
    return false;
  }
  const validation = await fetchApiJson('/prompts/validate', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      id: promptId,
      system_text: promptEditor.value,
    }),
  });
  setPromptValidation(validation.ok ? 'valid' : validation.errors, validation.ok ? 'ok' : 'warn');
  return validation.ok;
}

async function savePromptEditor() {
  const promptId = promptIdInput.value.trim();
  const isExistingPrompt = editingPromptId && editingPromptId === promptId && promptExists(promptId);
  setPromptManagerStatus('saving…');
  if (!(await validatePromptEditor())) {
    setPromptManagerStatus('fix validation errors', 'warn');
    return;
  }

  const response = await fetchApi(isExistingPrompt ? '/prompts/' + encodeURIComponent(promptId) : '/prompts', {
    method: isExistingPrompt ? 'PUT' : 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      id: promptId,
      system_text: promptEditor.value,
    }),
  });
  if (!response.ok) throw new Error(await readablePromptError(response));

  const saved = await response.json();
  creatingPrompt = false;
  editingPromptId = saved.id;
  await refreshPromptsForUi(saved.id);
  setPromptManagerStatus(isExistingPrompt ? 'saved' : 'created', 'ok');
}

async function setEditorPromptActive() {
  const promptId = selectedManagerPromptId();
  if (!promptId) return;
  setPromptManagerStatus('setting active…');
  const state = await fetchApiJson('/prompt-state', {
    method: 'PUT',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      active_prompt_id: promptId,
      updated_by: 'scratchpad-manager',
    }),
  });
  activePromptId = state.active_prompt_id;
  lastInputSentToLLM = '';
  await refreshPromptsForUi(activePromptId);
  promptPicker.value = activePromptId;
  setPromptManagerStatus('active: ' + activePromptId, 'ok');
}

async function archiveEditorPrompt() {
  const promptId = selectedManagerPromptId();
  if (!promptId) return;
  if (!window.confirm('Archive prompt "' + promptId + '"?')) return;
  setPromptManagerStatus('archiving…');
  const response = await fetchApi('/prompts/' + encodeURIComponent(promptId) + '/archive', {method: 'POST'});
  if (!response.ok) throw new Error(await readablePromptError(response));
  const state = await response.json();
  activePromptId = state.active_prompt_id || '';
  creatingPrompt = false;
  editingPromptId = '';
  promptIdInput.value = '';
  promptEditor.value = '';
  await refreshPromptsForUi(activePromptId);
  setPromptManagerStatus('archived ' + promptId, 'ok');
}

async function readablePromptError(response) {
  try {
    const body = await response.clone().json();
    if (Array.isArray(body.detail)) return body.detail.join('; ');
    if (body.detail) return body.detail;
  } catch (err) {
    // Fall through to generic text below; malformed error bodies should
    // not hide the original HTTP status from the user.
  }
  return 'HTTP ' + response.status + ' ' + (await response.text()).slice(0, 200);
}

function runPromptManagerAction(action) {
  action().catch((err) => {
    console.warn('prompt manager action failed', err);
    setPromptManagerStatus('prompt action failed', 'warn');
    setPromptValidation(err.message || String(err), 'warn');
  });
}

promptManagerToggle.addEventListener('click', () => {
  const willOpen = promptManager.hidden;
  promptManager.hidden = !willOpen;
  promptManagerToggle.textContent = willOpen ? 'Hide prompts' : 'Prompts';
  promptManagerToggle.setAttribute('aria-expanded', String(willOpen));
  if (willOpen) {
    setPromptManagerStatus(apiAvailable ? 'open' : 'api unavailable', apiAvailable ? '' : 'warn');
    runPromptManagerAction(async () => {
      await refreshPromptsForUi(activePromptId);
      if (activePromptId) await loadPromptIntoEditor(activePromptId);
    });
  }
});
promptManagerList.addEventListener('change', () => runPromptManagerAction(() => loadPromptIntoEditor(promptManagerList.value)));
promptNewBtn.addEventListener('click', startNewPrompt);
promptValidateBtn.addEventListener('click', () => runPromptManagerAction(validatePromptEditor));
promptSaveBtn.addEventListener('click', () => runPromptManagerAction(savePromptEditor));
promptSetActiveBtn.addEventListener('click', () => runPromptManagerAction(setEditorPromptActive));
promptArchiveBtn.addEventListener('click', () => runPromptManagerAction(archiveEditorPrompt));
promptIdInput.addEventListener('input', renderPromptManagerList);

function updateApiLinks() {
  if (!apiBase) return;
  apiPromptsLink.href = apiBase + '/prompts/preview';
  apiDocsLink.href = apiBase.replace(/\/api$/, '') + '/docs';
}

function setApiHealthStatus(health) {
  const status = health && health.status ? health.status : 'unknown';
  const apiLabel = apiBase ? ' @ ' + apiBase.replace(/^https?:\/\//, '') : '';
  apiHealthStatus.textContent = 'api: ' + status + apiLabel;
  apiHealthStatus.title = JSON.stringify({base: apiBase || null, ...(health || {status})});
  apiHealthStatus.className = status === 'ok' ? 'ok' : 'warn';
}

async function initApi() {
  if (apiDiscoveryInFlight) return;
  apiDiscoveryInFlight = true;
  for (const candidateApiBase of API_BASE_CANDIDATES) {
    try {
      const health = await fetchHealthFromApiBase(candidateApiBase);
      const prompts = await fetchJsonFromApiBase(candidateApiBase, '/prompts');
      const state = await fetchJsonFromApiBase(candidateApiBase, '/prompt-state');
      apiBase = candidateApiBase;
      apiAvailable = true;
      setApiHealthStatus(health);
      renderPromptPicker(prompts, state);
      updateApiLinks();
      apiDiscoveryInFlight = false;
      pushScratchpadState(currentOutgoingKind());
      startApiHealthPolling();
      return;
    } catch (err) {
      console.info(candidateApiBase + ' prompt state unavailable', err);
    }
  }
  apiBase = '';
  apiAvailable = false;
  promptPicker.disabled = true;
  renderPromptManagerList();
  setApiHealthStatus({status: 'offline'});
  console.info('/api prompt state unavailable; transforms will fail open to raw text');
  apiDiscoveryInFlight = false;
  startApiHealthPolling();
}

promptPicker.addEventListener('change', async () => {
  const previousPromptId = activePromptId;
  activePromptId = promptPicker.value;
  lastInputSentToLLM = '';
  try {
    const state = await fetchApiJson('/prompt-state', {
      method: 'PUT',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({
        active_prompt_id: activePromptId,
        updated_by: 'scratchpad',
      }),
    });
    activePromptId = state.active_prompt_id;
    promptPicker.value = activePromptId;
    renderPromptManagerList();
    setStatus(aiEnabled ? 'prompt set' : 'off', aiEnabled ? 'ok' : '');
  } catch (err) {
    console.warn('PUT /api/prompt-state failed', err);
    activePromptId = previousPromptId;
    promptPicker.value = previousPromptId;
    setStatus('prompt failed', 'warn');
  }
});

/*
 * ===========================================================
 *  Scratchpad runtime state
 * ===========================================================
 *
 * Raycast has a backend-owned read path for the text the page considers
 * sendable. That breaks the old coupling where a
 * send-to-* script had to refocus Chrome, Cmd+A/Cmd+C whatever textarea
 * happened to be active, and hope it captured the intended pane. The
 * browser still owns this state because it owns the textareas; the API
 * mirrors the current AI toggle, raw dictation, and outgoing
 * text for non-DOM clients.
 */
let scratchpadStateTimer = null;

function currentOutgoingText() {
  return aiEnabled ? padOut.value : pad.value;
}

function currentOutgoingKind() {
  const outgoingText = currentOutgoingText();
  if (!outgoingText) return 'empty';
  if (!aiEnabled) return 'raw';
  if (outgoingText === pad.value) return 'raw';
  return 'edited';
}

function pushScratchpadState(outgoingKind) {
  if (!apiAvailable || !apiBase) return;
  fetchApi('/scratchpad-state', {
    method: 'PUT',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      ai_enabled: aiEnabled,
      raw_text: pad.value,
      outgoing_text: currentOutgoingText(),
      outgoing_kind: outgoingKind || currentOutgoingKind(),
    }),
  }).catch((err) => console.warn('PUT /api/scratchpad-state failed', err));
}

function scheduleScratchpadStatePush() {
  clearTimeout(scratchpadStateTimer);
  scratchpadStateTimer = setTimeout(() => pushScratchpadState(currentOutgoingKind()), 150);
}

pad.addEventListener('input', scheduleScratchpadStatePush);
padOut.addEventListener('input', scheduleScratchpadStatePush);

initApi();

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
    setPreviewStatus('raw');
    setStatus('off');
    pushScratchpadState('raw');
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
  if (!aiEnabled) {
    clearTimeout(debounceTimer);
    if (inFlight) { inFlight.abort(); inFlight = null; }
    padOut.value = pad.value;
    setPreviewStatus('raw');
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
    setPreviewStatus('');
    setStatus('idle');
  }
  applyAiVisibility();
  pushScratchpadState(currentOutgoingKind());
});

function scheduleTransform() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runTransform, TRANSFORM_DEBOUNCE_MS);
}

async function runTransform() {
  const text = pad.value;
  if (!text) { setStatus('idle'); setPreviewStatus(''); return; }
  if (text === lastInputSentToLLM) return;
  lastInputSentToLLM = text;

  // Cancel any in-flight call so the freshest dictation always wins.
  if (inFlight) inFlight.abort();
  const controller = new AbortController();
  inFlight = controller;
  const runId = ++transformRunId;

  setStatus('transforming…', 'busy');
  try {
    await ensureApiAvailable();
    const result = await requestTransform(text, controller.signal);
    if (runId !== transformRunId) return;
    const cleaned = result.cleanedText;
    // Debug visibility — open DevTools (⌥⌘I) → Console to see each
    // round-trip. Cheap, removable, makes "is the LLM doing nothing
    // vs is it returning something different I can't tell apart"
    // distinguishable.
    console.log('[transform]', {input: text, output: cleaned, changed: cleaned !== text, status: result.status});
    padOut.value = cleaned;
    // Programmatic value assignment doesn't trigger native "scroll caret into view"
    // like user keystrokes do. Ensure the caret stays visible if padOut has focus.
    if (document.activeElement === padOut) ensureCaretInView(padOut);
    setPreviewStatus(describePreview(text, cleaned, result.status));
    setStatus(describeTransformStatus(text, cleaned, result.status), result.ok ? 'ok' : 'warn');
    pushScratchpadState(result.ok ? 'cleaned' : 'raw');
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (runId !== transformRunId) return;
    // Fail-open: never block the user. Drop the raw text into the
    // output pane so the existing send-script flow still works,
    // and surface that we did so.
    console.warn('transform failed, falling back to raw text', err);
    padOut.value = text;
    // Programmatic value assignment doesn't trigger native "scroll caret into view"
    // like user keystrokes do. Ensure the caret stays visible if padOut has focus.
    if (document.activeElement === padOut) ensureCaretInView(padOut);
    setPreviewStatus('raw fallback');
    setStatus('fail-open: raw', 'warn');
    pushScratchpadState('raw');
  } finally {
    if (inFlight === controller) inFlight = null;
    updateFauxCaret();
  }
}

async function requestTransform(text, signal) {
  const r = await fetch(apiBase + '/transforms', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({
      raw_text: text,
      prompt_id: activePromptId || undefined,
      source: 'scratchpad',
    }),
    signal,
  });
  if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + (await r.text()).slice(0, 200));
  const body = await r.json();
  activePromptId = body.prompt_id || activePromptId;
  if (activePromptId && promptPicker.value !== activePromptId) promptPicker.value = activePromptId;
  return {
    cleanedText: body.cleaned_text,
    status: body.status,
    ok: body.status === 'ok',
    failureReason: body.failure_reason,
  };
}

function describePreview(rawText, cleanedText, status) {
  if (status && status !== 'ok') return status.replace(/_/g, ' ');
  if (rawText === cleanedText) return 'unchanged';
  return rawText.length + ' → ' + cleanedText.length + ' chars';
}

function describeTransformStatus(rawText, cleanedText, status) {
  if (status && status !== 'ok') return 'fail-open: raw';
  return cleanedText === rawText ? 'ok (unchanged)' : 'ok';
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
 * Faux-caret positioning.
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
  if (!(ta instanceof HTMLTextAreaElement) || (ta !== pad && ta !== padOut)) {
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
