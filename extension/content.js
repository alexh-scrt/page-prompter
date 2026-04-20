/**
 * content.js – page_prompter content script
 *
 * Injected into every page the user visits. Responsible for:
 *  - Entering / exiting "annotation mode" when instructed by the popup.
 *  - Highlighting DOM elements as the user hovers over them.
 *  - Opening an inline dialog so the user can type a comment for a clicked element.
 *  - Computing a unique CSS selector for the clicked element.
 *  - Capturing a small HTML context snippet (the element's outer HTML).
 *  - Persisting annotations to chrome.storage.session keyed by tab ID.
 *  - Rendering sticky-note overlays on top of annotated elements.
 *  - Responding to popup requests to retrieve, update, and delete annotations.
 *
 * Message protocol (from popup / background → content script)
 * -----------------------------------------------------------
 * { action: 'startAnnotating' }         – enter annotation mode
 * { action: 'stopAnnotating' }          – exit annotation mode
 * { action: 'getAnnotations' }          – return all annotations for this page
 * { action: 'deleteAnnotation', id }    – remove a single annotation by id
 * { action: 'updateAnnotation', annotation } – replace annotation by id
 * { action: 'clearAnnotations' }        – remove all annotations for this page
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** @type {boolean} Whether annotation-picking mode is currently active. */
let annotationModeActive = false;

/** @type {Element|null} The element currently highlighted by the hover picker. */
let highlightedElement = null;

/** @type {HTMLElement|null} The currently open comment dialog, if any. */
let activeDialog = null;

/** @type {Map<string, object>} In-memory cache of annotations for this page. */
let annotationsCache = new Map();

// ---------------------------------------------------------------------------
// Initialisation – restore any persisted annotations on page load
// ---------------------------------------------------------------------------

(async function init() {
  try {
    const stored = await loadAnnotations();
    annotationsCache = new Map(stored.map(a => [a.annotation_id, a]));
    renderAllStickyNotes();
  } catch (err) {
    console.warn('[page_prompter] Failed to load persisted annotations:', err);
  }
})();

// ---------------------------------------------------------------------------
// Chrome runtime message listener
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message.action) {
    case 'startAnnotating':
      startAnnotationMode();
      sendResponse({ success: true });
      break;

    case 'stopAnnotating':
      stopAnnotationMode();
      sendResponse({ success: true });
      break;

    case 'getAnnotations':
      sendResponse({ annotations: Array.from(annotationsCache.values()) });
      break;

    case 'deleteAnnotation':
      deleteAnnotation(message.id);
      sendResponse({ success: true });
      break;

    case 'updateAnnotation':
      updateAnnotation(message.annotation);
      sendResponse({ success: true });
      break;

    case 'clearAnnotations':
      clearAllAnnotations();
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: `Unknown action: ${message.action}` });
  }
  // Return true to allow async sendResponse in future extensions of this code.
  return true;
});

// ---------------------------------------------------------------------------
// Annotation mode – enter / exit
// ---------------------------------------------------------------------------

/**
 * Enter annotation-picking mode.
 * Attaches hover and click listeners, adds a visual indicator to the page.
 */
function startAnnotationMode() {
  if (annotationModeActive) return;
  annotationModeActive = true;

  document.addEventListener('mouseover', onMouseOver, true);
  document.addEventListener('mouseout', onMouseOut, true);
  document.addEventListener('click', onClick, true);
  document.addEventListener('keydown', onKeyDown, true);

  showModeIndicator();
}

/**
 * Exit annotation-picking mode.
 * Removes event listeners and cleans up UI.
 */
function stopAnnotationMode() {
  if (!annotationModeActive) return;
  annotationModeActive = false;

  document.removeEventListener('mouseover', onMouseOver, true);
  document.removeEventListener('mouseout', onMouseOut, true);
  document.removeEventListener('click', onClick, true);
  document.removeEventListener('keydown', onKeyDown, true);

  clearHighlight();
  hideModeIndicator();

  if (activeDialog) {
    activeDialog.remove();
    activeDialog = null;
  }
}

// ---------------------------------------------------------------------------
// Event handlers for annotation mode
// ---------------------------------------------------------------------------

/**
 * @param {MouseEvent} event
 */
function onMouseOver(event) {
  const target = /** @type {Element} */ (event.target);
  if (isPagePrompterElement(target)) return;

  clearHighlight();
  highlightedElement = target;
  target.classList.add('pp-highlight');
}

/**
 * @param {MouseEvent} event
 */
function onMouseOut(event) {
  const target = /** @type {Element} */ (event.target);
  if (isPagePrompterElement(target)) return;
  target.classList.remove('pp-highlight');
  if (highlightedElement === target) {
    highlightedElement = null;
  }
}

/**
 * @param {MouseEvent} event
 */
function onClick(event) {
  const target = /** @type {Element} */ (event.target);
  if (isPagePrompterElement(target)) return;

  event.preventDefault();
  event.stopPropagation();

  clearHighlight();
  openAnnotationDialog(target);
}

/**
 * @param {KeyboardEvent} event
 */
function onKeyDown(event) {
  if (event.key === 'Escape') {
    if (activeDialog) {
      activeDialog.remove();
      activeDialog = null;
    } else {
      stopAnnotationMode();
      // Notify the popup that annotation mode has been cancelled.
      chrome.runtime.sendMessage({ action: 'annotationModeStopped' }).catch(() => {});
    }
  }
}

// ---------------------------------------------------------------------------
// Highlight helpers
// ---------------------------------------------------------------------------

function clearHighlight() {
  if (highlightedElement) {
    highlightedElement.classList.remove('pp-highlight');
    highlightedElement = null;
  }
}

// ---------------------------------------------------------------------------
// Mode indicator banner
// ---------------------------------------------------------------------------

/**
 * Show a fixed banner at the top of the page telling the user they are in
 * annotation mode.
 */
function showModeIndicator() {
  if (document.getElementById('pp-mode-indicator')) return;

  const banner = document.createElement('div');
  banner.id = 'pp-mode-indicator';
  banner.setAttribute('data-pp', 'true');
  banner.textContent = '🔍 page_prompter: Click any element to annotate it. Press Esc to exit.';
  document.body.appendChild(banner);
}

function hideModeIndicator() {
  const banner = document.getElementById('pp-mode-indicator');
  if (banner) banner.remove();
}

// ---------------------------------------------------------------------------
// Annotation dialog
// ---------------------------------------------------------------------------

/**
 * Open an inline dialog anchored near the clicked element, allowing the user
 * to type a comment before saving the annotation.
 *
 * @param {Element} element – The annotated DOM element.
 */
function openAnnotationDialog(element) {
  // Remove any existing dialog first.
  if (activeDialog) {
    activeDialog.remove();
    activeDialog = null;
  }

  const selector = computeSelector(element);
  const htmlContext = element.outerHTML.slice(0, 500); // Limit context size

  const dialog = document.createElement('div');
  dialog.className = 'pp-dialog';
  dialog.setAttribute('data-pp', 'true');

  dialog.innerHTML = `
    <div class="pp-dialog-header">
      <span class="pp-dialog-title">Add Annotation</span>
      <button class="pp-dialog-close" title="Cancel">✕</button>
    </div>
    <div class="pp-dialog-selector" title="CSS selector for this element">${escapeHtml(selector)}</div>
    <textarea class="pp-dialog-textarea" placeholder="Describe the change or instruction for this element…" rows="4"></textarea>
    <div class="pp-dialog-actions">
      <button class="pp-dialog-cancel">Cancel</button>
      <button class="pp-dialog-save">Save Annotation</button>
    </div>
  `;

  // Position the dialog near the element
  positionDialog(dialog, element);

  document.body.appendChild(dialog);
  activeDialog = dialog;

  // Focus the textarea
  const textarea = dialog.querySelector('.pp-dialog-textarea');
  textarea.focus();

  // Wire up buttons
  dialog.querySelector('.pp-dialog-close').addEventListener('click', () => {
    dialog.remove();
    activeDialog = null;
  });

  dialog.querySelector('.pp-dialog-cancel').addEventListener('click', () => {
    dialog.remove();
    activeDialog = null;
  });

  dialog.querySelector('.pp-dialog-save').addEventListener('click', () => {
    const comment = textarea.value.trim();
    if (!comment) {
      textarea.classList.add('pp-textarea-error');
      textarea.placeholder = 'Please enter an instruction before saving.';
      return;
    }
    saveAnnotation({
      annotation_id: generateId(),
      element_selector: selector,
      comment,
      page_url: window.location.href,
      html_context: htmlContext,
    });
    dialog.remove();
    activeDialog = null;
  });

  // Allow Ctrl+Enter or Cmd+Enter to save
  textarea.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      dialog.querySelector('.pp-dialog-save').click();
    }
  });
}

/**
 * Position the dialog near the given element without going off-screen.
 *
 * @param {HTMLElement} dialog
 * @param {Element} element
 */
function positionDialog(dialog, element) {
  const rect = element.getBoundingClientRect();
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  // Estimate dialog dimensions before it is attached (use defaults)
  const dialogWidth = 340;
  const dialogHeight = 220;

  let top = rect.bottom + scrollY + 8;
  let left = rect.left + scrollX;

  // Clamp to viewport horizontally
  if (left + dialogWidth > scrollX + viewportWidth - 16) {
    left = scrollX + viewportWidth - dialogWidth - 16;
  }
  if (left < scrollX + 8) {
    left = scrollX + 8;
  }

  // If the dialog would go below the viewport, show it above the element
  if (top + dialogHeight > scrollY + viewportHeight - 16) {
    top = rect.top + scrollY - dialogHeight - 8;
  }
  if (top < scrollY + 8) {
    top = scrollY + 8;
  }

  dialog.style.top = `${top}px`;
  dialog.style.left = `${left}px`;
}

// ---------------------------------------------------------------------------
// Annotation persistence (chrome.storage.session)
// ---------------------------------------------------------------------------

/**
 * Derive a storage key unique to this page URL.
 * @returns {string}
 */
function storageKey() {
  return `pp_annotations_${window.location.href}`;
}

/**
 * Load all annotations for the current page from chrome.storage.session.
 * @returns {Promise<object[]>}
 */
async function loadAnnotations() {
  return new Promise((resolve) => {
    chrome.storage.session.get([storageKey()], (result) => {
      resolve(result[storageKey()] || []);
    });
  });
}

/**
 * Persist the current in-memory annotations cache to chrome.storage.session.
 * @returns {Promise<void>}
 */
async function persistAnnotations() {
  return new Promise((resolve) => {
    chrome.storage.session.set(
      { [storageKey()]: Array.from(annotationsCache.values()) },
      resolve
    );
  });
}

/**
 * Save a new annotation, persist it, and render its sticky note.
 * @param {object} annotation
 */
async function saveAnnotation(annotation) {
  annotationsCache.set(annotation.annotation_id, annotation);
  await persistAnnotations();
  renderStickyNote(annotation);
  // Notify the popup that a new annotation was added.
  chrome.runtime.sendMessage({ action: 'annotationAdded', annotation }).catch(() => {});
}

/**
 * Delete an annotation by ID, persist the change, and remove its sticky note.
 * @param {string} id
 */
async function deleteAnnotation(id) {
  annotationsCache.delete(id);
  await persistAnnotations();
  removeStickyNote(id);
}

/**
 * Replace an existing annotation (same ID) with updated data.
 * @param {object} annotation
 */
async function updateAnnotation(annotation) {
  annotationsCache.set(annotation.annotation_id, annotation);
  await persistAnnotations();
  // Re-render the sticky note with updated text
  removeStickyNote(annotation.annotation_id);
  renderStickyNote(annotation);
}

/**
 * Remove all annotations for this page and clear all sticky notes.
 */
async function clearAllAnnotations() {
  annotationsCache.clear();
  await persistAnnotations();
  document.querySelectorAll('.pp-sticky-note').forEach(n => n.remove());
}

// ---------------------------------------------------------------------------
// Sticky note rendering
// ---------------------------------------------------------------------------

/**
 * Render a sticky note overlay for a single annotation.
 * The note is absolutely positioned over the annotated element.
 *
 * @param {object} annotation
 */
function renderStickyNote(annotation) {
  // Avoid duplicates
  removeStickyNote(annotation.annotation_id);

  let target;
  try {
    target = document.querySelector(annotation.element_selector);
  } catch (_) {
    // Selector may be invalid on a different page load
    target = null;
  }

  if (!target) return;

  const rect = target.getBoundingClientRect();
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;

  const note = document.createElement('div');
  note.className = 'pp-sticky-note';
  note.setAttribute('data-pp', 'true');
  note.setAttribute('data-annotation-id', annotation.annotation_id);

  note.style.top = `${rect.top + scrollY}px`;
  note.style.left = `${rect.right + scrollX + 4}px`;

  note.innerHTML = `
    <div class="pp-note-selector" title="${escapeHtml(annotation.element_selector)}">${escapeHtml(truncate(annotation.element_selector, 40))}</div>
    <div class="pp-note-comment">${escapeHtml(annotation.comment)}</div>
    <button class="pp-note-delete" data-id="${escapeHtml(annotation.annotation_id)}" title="Delete annotation">✕</button>
  `;

  note.querySelector('.pp-note-delete').addEventListener('click', (e) => {
    e.stopPropagation();
    const id = e.currentTarget.getAttribute('data-id');
    deleteAnnotation(id);
    chrome.runtime.sendMessage({ action: 'annotationDeleted', id }).catch(() => {});
  });

  document.body.appendChild(note);
}

/**
 * Remove the sticky note DOM element for a given annotation ID.
 * @param {string} id
 */
function removeStickyNote(id) {
  const existing = document.querySelector(`.pp-sticky-note[data-annotation-id="${CSS.escape(id)}"]`);
  if (existing) existing.remove();
}

/**
 * Render sticky notes for all cached annotations (e.g. after page load).
 */
function renderAllStickyNotes() {
  for (const annotation of annotationsCache.values()) {
    renderStickyNote(annotation);
  }
}

// ---------------------------------------------------------------------------
// CSS selector computation
// ---------------------------------------------------------------------------

/**
 * Compute a reasonably unique CSS selector for a given element.
 *
 * Strategy (in order of preference):
 *  1. If the element has a unique ID, use `#id`.
 *  2. Build a path of tag + class + nth-child selectors up to the root,
 *     stopping once a unique match is found in the document.
 *
 * @param {Element} element
 * @returns {string} A CSS selector string.
 */
function computeSelector(element) {
  // 1. Unique ID
  if (element.id && document.querySelectorAll(`#${CSS.escape(element.id)}`).length === 1) {
    return `#${element.id}`;
  }

  // 2. Build ancestor path
  const parts = [];
  let current = element;

  while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
    let part = current.tagName.toLowerCase();

    // Add classes (limit to first 2 to keep selector manageable)
    if (current.classList && current.classList.length > 0) {
      const classes = Array.from(current.classList)
        .filter(c => !c.startsWith('pp-')) // Exclude our own classes
        .slice(0, 2)
        .map(c => `.${CSS.escape(c)}`)
        .join('');
      if (classes) part += classes;
    }

    // Add nth-child to disambiguate siblings with same tag+class
    const parent = current.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(
        sibling => sibling.tagName === current.tagName
      );
      if (siblings.length > 1) {
        const index = siblings.indexOf(current) + 1;
        part += `:nth-child(${index})`;
      }
    }

    parts.unshift(part);
    current = current.parentElement;

    // Check if the selector so far is already unique enough
    const candidate = parts.join(' > ');
    try {
      if (document.querySelectorAll(candidate).length === 1) {
        return candidate;
      }
    } catch (_) {
      // Malformed selector – continue building
    }
  }

  const fullSelector = parts.join(' > ');
  return fullSelector || element.tagName.toLowerCase();
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/**
 * Return true if the element (or any ancestor) is a page_prompter UI element
 * so we can prevent recursively annotating our own overlays.
 *
 * @param {Element} element
 * @returns {boolean}
 */
function isPagePrompterElement(element) {
  if (!element || typeof element.closest !== 'function') return false;
  return (
    element.closest('[data-pp="true"]') !== null ||
    element.classList.contains('pp-highlight') ||
    element.id === 'pp-mode-indicator'
  );
}

/**
 * Generate a random UUID-like string.
 * @returns {string}
 */
function generateId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Escape HTML special characters to prevent XSS in innerHTML.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(str).replace(/[&<>"']/g, m => map[m]);
}

/**
 * Truncate a string to a maximum length, appending '…' if needed.
 * @param {string} str
 * @param {number} max
 * @returns {string}
 */
function truncate(str, max) {
  return str.length > max ? str.slice(0, max - 1) + '\u2026' : str;
}
