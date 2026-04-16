/* frontend/js/shared.js
 * Shared utilities for all MoTitle pages.
 * Loaded AFTER font-preview.js and Socket.IO CDN script.
 */
'use strict';

const API_BASE = 'http://localhost:5001';

/** XSS-safe HTML entity escape */
function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Format seconds → "MM:SS.mmm" or "H:MM:SS.mmm" */
function formatTime(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const h  = Math.floor(seconds / 3600);
  const m  = Math.floor((seconds % 3600) / 60);
  const s  = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  const mm = String(ms).padStart(3, '0');
  if (h > 0) return `${h}:${_p(m)}:${_p(s)}.${mm}`;
  return `${_p(m)}:${_p(s)}.${mm}`;
}
function _p(n) { return String(n).padStart(2, '0'); }

/**
 * Show a floating toast message.
 * @param {string} message
 * @param {'success'|'error'|'info'} type
 * @param {number} durationMs
 */
function showToast(message, type = 'info', durationMs = 3000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-show'));
  setTimeout(() => {
    toast.classList.remove('toast-show');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }, durationMs);
}

/**
 * Connect Socket.IO, wire event handlers, initialise FontPreview.
 *
 * @param {Object} handlers  - { eventName: callbackFn }
 * @param {Object} options
 * @param {Function} [options.onConnect]    - fired on socket 'connect'
 * @param {Function} [options.onDisconnect] - fired on socket 'disconnect'
 * @param {boolean}  [options.optional]     - if true, failure is non-fatal
 * @returns {Object|null} Socket.IO socket instance, or null
 */
function connectSocket(handlers = {}, options = {}) {
  if (typeof io === 'undefined') {
    if (!options.optional) console.error('[connectSocket] Socket.IO not loaded');
    return null;
  }
  const socket = io(API_BASE, {
    transports: ['websocket', 'polling'],
    reconnectionDelay: 2000,
    reconnectionAttempts: 10,
  });
  // Always wire font preview
  if (typeof FontPreview !== 'undefined') FontPreview.init(socket);
  socket.on('connect',    () => options.onConnect?.());
  socket.on('disconnect', () => options.onDisconnect?.());
  for (const [event, fn] of Object.entries(handlers)) {
    socket.on(event, fn);
  }
  return socket;
}
