/**
 * live-message.js — what the dashboard does with one message of a live run.
 *
 * Shared by the WebSocket client and the SSE fallback. Each used to carry its
 * own copy, and the copies drifted: the SSE one never learnt `activations` or
 * the folds that arrive with `complete`, and neither took `architecture`,
 * which the server sends so an open Network panel fills in.
 *
 * A seq is not unique across message types. A frame's milestones are sent
 * with the frame's own seq, right after it, and both clients dropped any
 * message whose seq was not above the last one taken — so a live page lost
 * nearly every milestone. Frames still arrive in seq order, so a frame at or
 * below the last one applied is a replay; a milestone or warning is known by
 * its seq and its kind, so a replay (a reconnect, a fallback) cannot apply one
 * twice.
 */

import {
  store,
  markRunFinished,
  pushFrame,
  pushMilestone,
  pushWarning,
} from './store.js';

/** Milestones and warnings already applied, by identity. Shared by both transports. */
const _applied = new Set();
/** run_id → the highest frame seq applied. */
const _lastFrame = new Map();

/** @param {object} msg */
function _identity(msg) {
  return `${msg.run_id ?? ''}|${msg.type}|${msg.seq}|${msg.payload?.kind ?? ''}`;
}

/** Forget what was applied (tests; a page that loads another run). */
export function resetLiveMessages() {
  _applied.clear();
  _lastFrame.clear();
}

/**
 * Apply one live message to the store.
 *
 * @param {object} msg  The server's envelope: {type, run_id, seq, payload}.
 * @returns {{seq: number|null, complete: boolean}}
 *   `seq` is the message's sequence number when it is part of the run's
 *   sequence (frames, milestones, warnings), for the client to resume from;
 *   `complete` says the run has ended and the client should stop.
 */
export function applyLiveMessage(msg) {
  if (!msg || !msg.type) return { seq: null, complete: false };
  const sequenced = ['story_frame', 'milestone', 'warning'].includes(msg.type);
  const seq = sequenced && Number.isInteger(msg.seq) ? msg.seq : null;

  switch (msg.type) {
    case 'story_frame': {
      const run = msg.run_id ?? '';
      if (seq !== null && seq <= (_lastFrame.get(run) ?? -Infinity)) break;
      if (seq !== null) _lastFrame.set(run, seq);
      pushFrame(msg.payload ?? msg);
      break;
    }

    case 'milestone':
    case 'warning': {
      if (!msg.payload) break;
      const id = _identity(msg);
      if (_applied.has(id)) break;
      _applied.add(id);
      if (msg.type === 'milestone') pushMilestone(msg.payload);
      else pushWarning(msg.payload);
      break;
    }

    case 'architecture':
      if (Array.isArray(msg.payload?.architecture) && msg.payload.architecture.length) {
        store.set({ architecture: msg.payload.architecture });
      }
      break;

    case 'activations':
      // Real per-layer activation magnitudes captured from the model. Not
      // sequenced with story frames (independent cadence) — always take latest.
      if (msg.payload?.layers) store.set({ activations: msg.payload.layers });
      break;

    case 'complete':
      markRunFinished(msg.payload);
      // Folds are ranked once the stream ends; a live page learns of them here.
      if (msg.payload?.cross_validation) {
        store.set({ crossValidation: msg.payload.cross_validation });
      }
      return { seq: null, complete: true };

    default:
      // 'ping' and anything newer than this page.
      break;
  }
  return { seq, complete: false };
}
