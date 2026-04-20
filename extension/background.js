/**
 * background.js – page_prompter background service worker (Manifest V3)
 *
 * Handles extension lifecycle events and acts as a message relay between the
 * popup and the active tab's content script when direct messaging is not
 * available (e.g. when the popup needs to send a command to a specific tab).
 *
 * Responsibilities:
 *  - Listen for the extension action click to toggle annotation mode
 *    (supplementary to the popup – the popup handles most UI).
 *  - Relay messages between popup and content script where needed.
 *  - Keep track of which tabs currently have annotation mode active so the
 *    popup icon badge can reflect the state.
 */

'use strict';

/** @type {Set<number>} Tab IDs that currently have annotation mode active. */
const annotatingTabs = new Set();

// ---------------------------------------------------------------------------
// Message relay
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case 'annotationModeStopped':
      if (sender.tab && sender.tab.id !== undefined) {
        annotatingTabs.delete(sender.tab.id);
        updateBadge(sender.tab.id, false);
      }
      sendResponse({ success: true });
      break;

    case 'annotationAdded':
    case 'annotationDeleted':
      // Just acknowledge; popup can refresh its list on next open.
      sendResponse({ success: true });
      break;

    case 'setAnnotationMode': {
      // Sent by the popup to set annotation mode on a specific tab.
      const tabId = message.tabId;
      const active = message.active;
      if (active) {
        annotatingTabs.add(tabId);
      } else {
        annotatingTabs.delete(tabId);
      }
      updateBadge(tabId, active);
      sendResponse({ success: true });
      break;
    }

    default:
      sendResponse({ error: `Unknown action: ${message.action}` });
  }
  return true;
});

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

/**
 * Update the extension action badge to indicate annotation mode state.
 *
 * @param {number} tabId
 * @param {boolean} active
 */
function updateBadge(tabId, active) {
  if (active) {
    chrome.action.setBadgeText({ text: 'ON', tabId });
    chrome.action.setBadgeBackgroundColor({ color: '#3b82f6', tabId });
  } else {
    chrome.action.setBadgeText({ text: '', tabId });
  }
}

// ---------------------------------------------------------------------------
// Tab cleanup – remove annotation-mode state when a tab is closed
// ---------------------------------------------------------------------------

chrome.tabs.onRemoved.addListener((tabId) => {
  annotatingTabs.delete(tabId);
});
