/**
 * sse-client.js — the live feed over Server-Sent Events, for when the
 * WebSocket upgrade is refused (ws-client hands over through onUnavailable).
 *
 * EventSource reconnects by itself, sending the id of the last event it
 * received as Last-Event-ID; the server resumes after it. The URL's last_seq
 * is only where the first connection starts.
 */

import { store } from './store.js';
import { applyLiveMessage } from './live-message.js';
import { withToken } from './auth.js';

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
  return withToken(`/sse/live/${_runId}?last_seq=${_lastSeq}`);
}

function _openSSE() {
  if (_stopped) return;

  _es = new EventSource(_sseUrl());

  _es.onopen = () => {
    store.set({ connected: true });
  };

  _es.onmessage = (evt) => {
    let msg;
    try {
      msg = JSON.parse(evt.data);
    } catch {
      return; // ignore malformed
    }
    const { seq, complete } = applyLiveMessage(msg);
    if (seq !== null) _lastSeq = Math.max(_lastSeq, seq);
    if (complete) disconnectSSE();
  };

  _es.onerror = () => {
    store.set({ connected: false });
    // EventSource reconnects automatically, with Last-Event-ID.
  };
}
