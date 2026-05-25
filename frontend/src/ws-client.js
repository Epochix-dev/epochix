/**
 * ws-client.js — WebSocket client with exponential backoff + last_seq tracking.
 *
 * Reconnect schedule: 1s → 2s → 4s → 8s → 16s → 30s (cap).
 * On reconnect sends ?last_seq=N so the server replays missed frames.
 */

import { store, pushFrame, pushMilestone, pushWarning } from './store.js';

const BACKOFF_INITIAL = 1000;
const BACKOFF_MAX = 30_000;
const HEARTBEAT_TIMEOUT = 45_000; // if no ping in 45s, reconnect

let _ws = null;
let _lastSeq = -1;
let _delay = BACKOFF_INITIAL;
let _runId = null;
let _heartbeatTimer = null;
let _reconnectTimer = null;
let _stopped = false;

/**
 * Start the WebSocket connection for a run.
 * @param {string} runId
 * @param {number} [initialSeq=-1]  Last seq already loaded from HTTP snapshot.
 */
export function connect(runId, initialSeq = -1) {
  _runId = runId;
  _lastSeq = initialSeq;
  _stopped = false;
  _delay = BACKOFF_INITIAL;
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

  _ws.onopen = () => {
    _delay = BACKOFF_INITIAL; // reset backoff on success
    store.set({ connected: true });
    _resetHeartbeat();
  };

  _ws.onmessage = (evt) => {
    _resetHeartbeat();
    try {
      const msg = JSON.parse(evt.data);
      _handleMessage(msg);
    } catch {
      // ignore malformed
    }
  };

  _ws.onerror = () => {
    // onerror always followed by onclose — let onclose handle reconnect
  };

  _ws.onclose = () => {
    clearTimeout(_heartbeatTimer);
    store.set({ connected: false });
    if (!_stopped) {
      _scheduleReconnect();
    }
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
      disconnect();
      break;

    default:
      break;
  }
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
