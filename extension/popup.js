/**
 * popup.js – page_prompter extension popup logic
 *
 * Responsibilities:
 *  - On open, query the active tab's content script for all stored annotations.
 *  - Render annotation cards in the list with edit and delete controls.
 *  - Toggle annotation-picking mode in the content script.
 *  - Send all annotations to the local Flask server (POST /export) and display
 *    the resulting prompts (plain text, XML, JSON) in the tabbed export panel.
 *  - Copy any format to the clipboard via the Clipboard API.
 *  - Keep the UI in sync as annotations are added / edited / deleted.
 *
 * Communication pattern:
 *  popup → content script via chrome.tabs.sendMessage
 *  popup → Flask server  via fetch (http://localhost:5000/export)
 */

'use strict';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Base URL of the local Flask server. */
const SERVER_BASE_URL = 'http://localhost:5000';

/** How long (ms) status messages stay visible before auto-hiding. */
const STATUS_DURATION_MS = 4000;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/**
 * All annotations for the current page, keyed by annotation_id.
 * @type {Map<string, object>}
 */
let annotationsMap = new Map();

/**
 * Whether annotation-picking mode is currently active on the page.
 * @type {boolean}
 */
let annotationModeActive = false;

/**
 * The numeric ID of the currently active browser tab.
 * @type {number|null}
 */
let currentTabId = null;

/**
 * Which export tab is currently shown ('plain' | 'xml' | 'json').
 * @type {string}
 */
let activeExportTab = 'plain';

// ---------------------------------------------------------------------------
// DOM references (resolved once on DOMContentLoaded)
// ---------------------------------------------------------------------------

/** @type {HTMLElement} */
let elAnnotationList;
/** @type {HTMLElement} */
let elEmptyState;
/** @type {HTMLElement} */
let elAnnotationCount;
/** @type {HTMLButtonElement} */
let elBtnToggleMode;
/** @type {HTMLButtonElement} */
let elBtnExport;
/** @type {HTMLButtonElement} */
let elBtnClear;
/** @type {HTMLElement} */
let elStatusBar;
/** @type {HTMLElement} */
let elExportPanel;

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  // Resolve DOM references
  elAnnotationList = document.getElementById('annotation-list');
  elEmptyState     = document.getElementById('empty-state');
  elAnnotationCount = document.getElementById('annotation-count');
  elBtnToggleMode  = document.getElementById('btn-toggle-mode');
  elBtnExport      = document.getElementById('btn-export');
  elBtnClear       = document.getElementById('btn-clear');
  elStatusBar      = document.getElementById('status-bar');
  elExportPanel    = document.getElementById('export-panel');

  // Bind static button events
  elBtnToggleMode.addEventListener('click', onToggleAnnotationMode);
  elBtnExport.addEventListener('click', onExportPrompts);
  elBtnClear.addEventListener('click', onClearAllAnnotations);

  // Bind export tab switching
  document.querySelectorAll('.export-tab').forEach((tab) => {
    tab.addEventListener('click', () => switchExportTab(tab.dataset.target));
  });

  // Bind copy buttons
  document.querySelectorAll('.btn-copy').forEach((btn) => {
    btn.addEventListener('click', () => onCopy(btn));
  });

  // Determine the active tab and load annotations
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id !== undefined) {
      currentTabId = tab.id;
      await loadAnnotationsFromPage();
    } else {
      showStatus('Could not determine the active tab.', 'error');
    }
  } catch (err) {
    showStatus(`Initialisation error: ${err.message}`, 'error');
  }
});

// ---------------------------------------------------------------------------
// Load annotations from content script
// ---------------------------------------------------------------------------

/**
 * Ask the content script for the current annotations and re-render the list.
 * @returns {Promise<void>}
 */
async function loadAnnotationsFromPage() {
  try {
    const response = await sendToContentScript({ action: 'getAnnotations' });
    if (response && Array.isArray(response.annotations)) {
      annotationsMap = new Map(
        response.annotations.map((a) => [a.annotation_id, a])
      );
    } else {
      annotationsMap = new Map();
    }
  } catch (_err) {
    // Content script may not be injected on restricted pages (e.g. chrome://)
    annotationsMap = new Map();
  }
  renderAnnotationList();
}

// ---------------------------------------------------------------------------
// Render annotation list
// ---------------------------------------------------------------------------

/**
 * Re-render the full annotation list from the current `annotationsMap`.
 */
function renderAnnotationList() {
  // Remove all existing cards but keep the empty-state element
  const cards = elAnnotationList.querySelectorAll('.annotation-card');
  cards.forEach((c) => c.remove());

  const count = annotationsMap.size;
  elAnnotationCount.textContent = String(count);

  if (count === 0) {
    elEmptyState.style.display = '';
    elBtnExport.disabled = true;
    elBtnClear.disabled = true;
    hideExportPanel();
    return;
  }

  elEmptyState.style.display = 'none';
  elBtnExport.disabled = false;
  elBtnClear.disabled = false;

  let index = 1;
  for (const annotation of annotationsMap.values()) {
    const card = buildAnnotationCard(annotation, index++);
    elAnnotationList.appendChild(card);
  }
}

/**
 * Build a DOM card for a single annotation.
 *
 * @param {object} annotation
 * @param {number} index  1-based display index
 * @returns {HTMLElement}
 */
function buildAnnotationCard(annotation, index) {
  const card = document.createElement('div');
  card.className = 'annotation-card';
  card.dataset.annotationId = annotation.annotation_id;

  // --- View mode markup ---------------------------------------------------
  const viewHtml = `
    <span class="card-index" aria-hidden="true">${index}</span><code
      class="card-selector"
      title="${escapeAttr(annotation.element_selector)}"
    >${escapeHtml(truncate(annotation.element_selector, 55))}</code>
    <div class="card-comment">${escapeHtml(annotation.comment)}</div>
    <div class="card-actions">
      <button
        class="btn-icon btn-edit"
        title="Edit this annotation"
        aria-label="Edit annotation"
      >✏️</button>
      <button
        class="btn btn-danger btn-delete"
        title="Delete this annotation"
        aria-label="Delete annotation"
      >✕ Delete</button>
    </div>
  `;

  card.innerHTML = viewHtml;

  // Wire up edit button
  card.querySelector('.btn-edit').addEventListener('click', () => {
    enterEditMode(card, annotation);
  });

  // Wire up delete button
  card.querySelector('.btn-delete').addEventListener('click', async () => {
    await onDeleteAnnotation(annotation.annotation_id);
  });

  return card;
}

/**
 * Switch a card into inline edit mode.
 *
 * @param {HTMLElement} card
 * @param {object} annotation
 */
function enterEditMode(card, annotation) {
  card.classList.add('editing');

  // Replace card contents with an edit form
  card.innerHTML = `
    <code
      class="card-selector"
      title="${escapeAttr(annotation.element_selector)}"
    >${escapeHtml(truncate(annotation.element_selector, 55))}</code>
    <textarea
      class="card-edit-textarea"
      aria-label="Edit annotation comment"
    >${escapeHtml(annotation.comment)}</textarea>
    <div class="card-edit-actions">
      <button class="btn-edit-cancel">Cancel</button>
      <button class="btn-edit-save">Save</button>
    </div>
  `;

  const textarea = card.querySelector('.card-edit-textarea');
  textarea.focus();
  // Move cursor to end
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  card.querySelector('.btn-edit-cancel').addEventListener('click', () => {
    // Restore view mode without saving
    card.classList.remove('editing');
    renderAnnotationList();
  });

  card.querySelector('.btn-edit-save').addEventListener('click', async () => {
    const newComment = textarea.value.trim();
    if (!newComment) {
      textarea.style.borderColor = '#ef4444';
      textarea.focus();
      return;
    }
    await onUpdateAnnotation({ ...annotation, comment: newComment });
  });

  // Ctrl+Enter / Cmd+Enter saves
  textarea.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      card.querySelector('.btn-edit-save').click();
    }
    if (e.key === 'Escape') {
      card.querySelector('.btn-edit-cancel').click();
    }
  });
}

// ---------------------------------------------------------------------------
// Annotation CRUD handlers
// ---------------------------------------------------------------------------

/**
 * Delete an annotation: update local state, notify content script, re-render.
 *
 * @param {string} annotationId
 * @returns {Promise<void>}
 */
async function onDeleteAnnotation(annotationId) {
  annotationsMap.delete(annotationId);
  renderAnnotationList();
  hideExportPanel();

  try {
    await sendToContentScript({ action: 'deleteAnnotation', id: annotationId });
  } catch (err) {
    // Best-effort – the in-memory state is already updated
    console.warn('[page_prompter popup] deleteAnnotation error:', err);
  }
}

/**
 * Update an existing annotation: update local state, notify content script,
 * re-render.
 *
 * @param {object} updatedAnnotation
 * @returns {Promise<void>}
 */
async function onUpdateAnnotation(updatedAnnotation) {
  annotationsMap.set(updatedAnnotation.annotation_id, updatedAnnotation);
  renderAnnotationList();
  hideExportPanel();

  try {
    await sendToContentScript({
      action: 'updateAnnotation',
      annotation: updatedAnnotation,
    });
  } catch (err) {
    console.warn('[page_prompter popup] updateAnnotation error:', err);
  }
}

/**
 * Clear all annotations: update local state, notify content script, re-render.
 *
 * @returns {Promise<void>}
 */
async function onClearAllAnnotations() {
  annotationsMap.clear();
  renderAnnotationList();
  hideExportPanel();

  try {
    await sendToContentScript({ action: 'clearAnnotations' });
  } catch (err) {
    console.warn('[page_prompter popup] clearAnnotations error:', err);
  }
}

// ---------------------------------------------------------------------------
// Annotation mode toggle
// ---------------------------------------------------------------------------

/**
 * Toggle annotation-picking mode on/off in the content script.
 * @returns {Promise<void>}
 */
async function onToggleAnnotationMode() {
  annotationModeActive = !annotationModeActive;
  updateAnnotationModeButton();

  const action = annotationModeActive ? 'startAnnotating' : 'stopAnnotating';

  try {
    await sendToContentScript({ action });

    // Update the background service worker badge
    if (currentTabId !== null) {
      chrome.runtime.sendMessage({
        action: 'setAnnotationMode',
        tabId: currentTabId,
        active: annotationModeActive,
      }).catch(() => {});
    }
  } catch (err) {
    // Revert the toggle if sending failed (e.g. restricted page)
    annotationModeActive = !annotationModeActive;
    updateAnnotationModeButton();
    showStatus(
      'Cannot annotate this page. Try a regular http/https page.',
      'error'
    );
  }

  // If annotation mode was turned on, close the popup so the user can
  // interact with the page directly. Chrome popup behaviour: the popup
  // closes automatically when focus leaves it, but we close explicitly.
  if (annotationModeActive) {
    window.close();
  }
}

/**
 * Update the toggle button label and style to reflect the current mode.
 */
function updateAnnotationModeButton() {
  if (annotationModeActive) {
    elBtnToggleMode.textContent = '⏹ Stop Annotating';
    elBtnToggleMode.classList.add('mode-active');
    elBtnToggleMode.title = 'Exit annotation-picking mode';
  } else {
    elBtnToggleMode.textContent = '🎯 Annotate';
    elBtnToggleMode.classList.remove('mode-active');
    elBtnToggleMode.title = 'Enter annotation-picking mode';
  }
}

// ---------------------------------------------------------------------------
// Export to Flask server
// ---------------------------------------------------------------------------

/**
 * Gather all annotations, POST them to the Flask /export endpoint, and
 * display the resulting prompts in the tabbed export panel.
 *
 * @returns {Promise<void>}
 */
async function onExportPrompts() {
  if (annotationsMap.size === 0) {
    showStatus('No annotations to export.', 'info');
    return;
  }

  // Determine page URL from the first annotation (all should share the same
  // page_url since annotations are scoped per page).
  const firstAnnotation = annotationsMap.values().next().value;
  const pageUrl = firstAnnotation.page_url || '';

  const annotations = Array.from(annotationsMap.values()).map((a) => ({
    annotation_id: a.annotation_id,
    element_selector: a.element_selector,
    comment: a.comment,
    page_url: a.page_url,
    html_context: a.html_context || '',
  }));

  // Show loading state
  const originalLabel = elBtnExport.innerHTML;
  elBtnExport.disabled = true;
  elBtnExport.innerHTML = '<span class="spinner"></span> Exporting…';
  showStatus('Contacting local server…', 'info');
  hideExportPanel();

  try {
    const response = await fetch(`${SERVER_BASE_URL}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_url: pageUrl, annotations }),
    });

    const data = await response.json();

    if (!response.ok) {
      const message = data.error || `Server returned ${response.status}.`;
      throw new Error(message);
    }

    // Populate export panel
    displayExportResult(data);
    showStatus(
      `✅ Exported ${data.annotation_count} annotation(s). Click a format tab to view and copy.`,
      'success'
    );
  } catch (err) {
    let userMessage = err.message;
    if (
      err instanceof TypeError &&
      err.message.toLowerCase().includes('failed to fetch')
    ) {
      userMessage =
        'Could not reach the local server. Is it running on http://localhost:5000?';
    }
    showStatus(`Export failed: ${userMessage}`, 'error');
  } finally {
    elBtnExport.disabled = false;
    elBtnExport.innerHTML = originalLabel;
  }
}

/**
 * Populate the export panel text areas with the server response and show the
 * panel.
 *
 * @param {object} data  The parsed JSON response from POST /export.
 */
function displayExportResult(data) {
  document.getElementById('export-plain-text').value =
    data.plain_text || '';
  document.getElementById('export-xml-prompt').value =
    data.xml_prompt || '';
  document.getElementById('export-json-schema').value =
    typeof data.json_schema === 'object'
      ? JSON.stringify(data.json_schema, null, 2)
      : String(data.json_schema || '');

  showExportPanel();
  // Default to plain text tab
  switchExportTab('tab-plain');
}

// ---------------------------------------------------------------------------
// Export panel visibility
// ---------------------------------------------------------------------------

function showExportPanel() {
  elExportPanel.classList.add('visible');
}

function hideExportPanel() {
  elExportPanel.classList.remove('visible');
  // Clear textarea contents to avoid stale data
  document.getElementById('export-plain-text').value = '';
  document.getElementById('export-xml-prompt').value = '';
  document.getElementById('export-json-schema').value = '';
}

// ---------------------------------------------------------------------------
// Export tab switching
// ---------------------------------------------------------------------------

/**
 * Switch the visible export tab.
 *
 * @param {string} targetId  The `id` of the tab content div to show.
 */
function switchExportTab(targetId) {
  const tabIds = ['tab-plain', 'tab-xml', 'tab-json'];

  tabIds.forEach((id) => {
    const contentEl = document.getElementById(id);
    if (contentEl) {
      contentEl.style.display = id === targetId ? '' : 'none';
    }
  });

  document.querySelectorAll('.export-tab').forEach((tab) => {
    const isActive = tab.dataset.target === targetId;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
  });

  activeExportTab = targetId;
}

// ---------------------------------------------------------------------------
// Copy to clipboard
// ---------------------------------------------------------------------------

/**
 * Copy the content of the textarea identified by `btn.dataset.copyTarget` to
 * the clipboard.
 *
 * @param {HTMLButtonElement} btn
 */
async function onCopy(btn) {
  const targetId = btn.dataset.copyTarget;
  const textarea = document.getElementById(targetId);
  if (!textarea || !textarea.value) return;

  try {
    await navigator.clipboard.writeText(textarea.value);
    btn.textContent = '✅ Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = '📋 Copy';
      btn.classList.remove('copied');
    }, 2000);
  } catch (_err) {
    // Fallback: select the text so the user can copy manually
    textarea.select();
    showStatus('Press Ctrl+C / Cmd+C to copy.', 'info');
  }
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

/** @type {number|null} */
let statusTimeout = null;

/**
 * Display a status message in the status bar.
 *
 * @param {string} message
 * @param {'success'|'error'|'info'} type
 */
function showStatus(message, type) {
  if (statusTimeout !== null) {
    clearTimeout(statusTimeout);
    statusTimeout = null;
  }

  elStatusBar.textContent = message;
  elStatusBar.className = `status-bar visible ${type}`;

  statusTimeout = setTimeout(() => {
    elStatusBar.classList.remove('visible');
    statusTimeout = null;
  }, STATUS_DURATION_MS);
}

// ---------------------------------------------------------------------------
// Chrome messaging helpers
// ---------------------------------------------------------------------------

/**
 * Send a message to the content script in the active tab and return its
 * response.
 *
 * @param {object} message
 * @returns {Promise<any>}
 */
function sendToContentScript(message) {
  return new Promise((resolve, reject) => {
    if (currentTabId === null) {
      reject(new Error('No active tab ID available.'));
      return;
    }
    chrome.tabs.sendMessage(currentTabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/**
 * Escape HTML special characters for safe insertion into innerHTML.
 *
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return String(str).replace(/[&<>"']/g, (m) => map[m]);
}

/**
 * Escape a string for use inside an HTML attribute value (double-quoted).
 *
 * @param {string} str
 * @returns {string}
 */
function escapeAttr(str) {
  return escapeHtml(str);
}

/**
 * Truncate a string to `max` characters, adding an ellipsis if needed.
 *
 * @param {string} str
 * @param {number} max
 * @returns {string}
 */
function truncate(str, max) {
  const s = String(str);
  return s.length > max ? s.slice(0, max - 1) + '\u2026' : s;
}
