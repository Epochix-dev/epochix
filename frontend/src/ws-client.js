/**
 * ws-client.js — WebSocket client with exponential backoff + last_seq tracking.
 *
 * Reconnect schedule: 1s → 2s → 4s → 8s → 16s → 30s (cap).
 * On reconnect sends ?last_seq=N so the server replays missed frames.
 *
 * When no connection has opened at all, the upgrade is being refused — a
 * proxy that blocks WebSockets answers the handshake and closes it. After
 * FALLBACK_AFTER such attempts the client hands over to `onUnavailable` (the
 * SSE feed). The fallback was chosen on `'WebSocket' in window`, which every
 * browser satisfies, so the documented SSE fallback never ran.
 */

import { store } from './store.js';
import { applyLiveMessage } from './live-message.js';

const BACKOFF_INITIAL = 1000;
const BACKOFF_MAX = 30_000;
const HEARTBEAT_TIMEOUT = 45_000; // if no ping in 45s, reconnect
const FALLBACK_AFTER = 2; // attempts that never opened, before falling back

let _ws = null;
let _lastSeq = -1;
let _delay = BACKOFF_INITIAL;
let _runId = null;
let _heartbeatTimer = null;
let _reconnectTimer = null;
let _stopped = false;
let _everOpened = false;
let _neverOpened = 0;
let _onUnavailable = null;

/**
 * Start the WebSocket connection for a run.
 * @param {string} runId
 * @param {number} [initialSeq=-1]  Last seq already loaded from HTTP snapshot.
 * @param {{onUnavailable?: (lastSeq: number) => void}} [options]
 *   Called once, with the last seq received, when the WebSocket cannot be
 *   opened at all; this client then stops.
 */
export function connect(runId, initialSeq = -1, { onUnavailable = null } = {}) {
  _runId = runId;
  _lastSeq = initialSeq;
  _stopped = false;
  _delay = BACKOFF_INITIAL;
  _everOpened = false;
  _neverOpened = 0;
  _onUnavailable = onUnavailable;
  _openSocket();
}

/** Permanently stop reconnecting (e.g. run is complete, page unloaded). */
export function disconnect() {
  _stopped = true;
  clearTimeout(_reconnectTimer);
  clearTimeout(_heartbeatTimer);
  if (_ws) {
    _ws.onclose = null;
    _ws.close();
    _ws = null;
  }
  store.set({ connected: false });
}

// ── internal ────────────────────────────────────────────────────────────────

function _wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws/live/${_runId}?last_seq=${_lastSeq}`;
}

function _openSocket() {
  if (_stopped) return;

  try {
    _ws = new WebSocket(_wsUrl());
  } catch (err) {
    console.warn('[ws] failed to open:', err);
    _scheduleReconnect();
    return;
  }

  let opened = false;
  _ws.onopen = () => {
    opened = true;
    _everOpened = true;
    _delay = BACKOFF_INITIAL; // reset backoff on success
    store.set({ connected: true });
    _resetHeartbeat();
  };

  _ws.onmessage = (evt) => {
    _resetHeartbeat();
    let msg;
    try {
      msg = JSON.parse(evt.data);
    } catch {
      return; // ignore malformed
    }
    const { seq, complete } = applyLiveMessage(msg);
    if (seq !== null) _lastSeq = Math.max(_lastSeq, seq);
    if (complete) disconnect();
  };

  _ws.onerror = () => {
    // onerror always followed by onclose — let onclose handle reconnect
  };

  _ws.onclose = () => {
    clearTimeout(_heartbeatTimer);
    store.set({ connected: false });
    if (_stopped) return;
    if (!opened) _neverOpened += 1;
    if (!_everOpened && _onUnavailable && _neverOpened >= FALLBACK_AFTER) {
      const handOver = _onUnavailable;
      const seq = _lastSeq;
      disconnect();
      handOver(seq);
      return;
    }
    _scheduleReconnect();
  };
}

function _resetHeartbeat() {
  clearTimeout(_heartbeatTimer);
  _heartbeatTimer = setTimeout(() => {
    // No message in 45 s — assume dead connection
    if (_ws) _ws.close();
  }, HEARTBEAT_TIMEOUT);
}

function _scheduleReconnect() {
  if (_stopped) return;
  _reconnectTimer = setTimeout(() => {
    _delay = Math.min(_delay * 2, BACKOFF_MAX);
    _openSocket();
  }, _delay);
}
