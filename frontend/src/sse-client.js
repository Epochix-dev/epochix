/**
 * sse-client.js — SSE fallback when WebSocket is unavailable.
 *
 * The browser's EventSource API has built-in reconnect. We layer
 * last_seq tracking on top so missed frames are replayed.
 */

import { store, pushFrame, pushMilestone, pushWarning } from './store.js';

let _es = null;
let _lastSeq = -1;
let _runId = null;
let _stopped = false;

/**
 * @param {string} runId
 * @param {number} [initialSeq=-1]
 */
export function connectSSE(runId, initialSeq = -1) {
  _runId = runId;
  _lastSeq = initialSeq;
  _stopped = false;
  _openSSE();
}

export function disconnectSSE() {
  _stopped = true;
  if (_es) {
    _es.close();
    _es = null;
  }
  store.set({ connected: false });
}

// ── internal ────────────────────────────────────────────────────────────────

function _sseUrl() {
  return `/sse/live/${_runId}?last_seq=${_lastSeq}`;
}

function _openSSE() {
  if (_stopped) return;

  _es = new EventSource(_sseUrl());

  _es.onopen = () => {
    store.set({ connected: true });
  };

  _es.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      _handleMessage(msg);
    } catch {
      // ignore
    }
  };

  _es.onerror = () => {
    store.set({ connected: false });
    // EventSource reconnects automatically; no manual action needed
  };
}

/** @param {object} msg */
function _handleMessage(msg) {
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case 'ping':
      break;
    case 'story_frame':
      if (msg.seq > _lastSeq) {
        _lastSeq = msg.seq;
        pushFrame(msg.payload ?? msg);
      }
      break;
    case 'milestone':
      if (msg.seq > _lastSeq) {
        _lastSeq = msg.seq;
        if (msg.payload) pushMilestone(msg.payload);
      }
      break;
    case 'warning':
      if (msg.seq > _lastSeq) {
        _lastSeq = msg.seq;
        if (msg.payload?.message) pushWarning(msg.payload.message);
      }
      break;
    case 'complete':
      store.set({ live: false, connected: false });
      disconnectSSE();
      break;
    default:
      break;
  }
}
