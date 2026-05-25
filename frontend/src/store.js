/**
 * store.js — minimal signals-based reactive store (~50 LOC)
 *
 * Usage:
 *   import { store } from './store.js';
 *   store.subscribe(state => renderGrade(state.currentFrame?.grade));
 *   store.set({ connected: true });
 */

/**
 * @template T
 * @param {T} initial
 * @returns {{ get: () => T, set: (patch: Partial<T>) => void, subscribe: (fn: (s: T) => void) => () => void }}
 */
export function createStore(initial) {
  let state = initial;
  /** @type {Set<(s: T) => void>} */
  const subs = new Set();
  return {
    get: () => state,
    set: (patch) => {
      state = { ...state, ...patch };
      subs.forEach((f) => f(state));
    },
    subscribe: (fn) => {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}

/**
 * @typedef {Object} AppState
 * @property {object|null}  run           - Run metadata
 * @property {object[]}     frames        - All StoryFrames received
 * @property {object|null}  currentFrame  - The frame currently displayed
 * @property {object[]}     metrics       - MetricEvents for engineer panel
 * @property {boolean}      connected     - WebSocket / SSE connected
 * @property {boolean}      live          - Run is still in progress
 * @property {string}       locale        - 'en' | 'fa' | 'fr'
 * @property {string}       theme         - 'dark' | 'light'
 * @property {number}       scrubEpoch    - -1 = latest, else pinned epoch
 * @property {string[]}     warnings      - Active warning messages
 * @property {object[]}     milestones    - All milestones received
 * @property {object[]|null} architecture - Parsed model layers [{name,layer_type,params,tech_label,plain_label,visual_type}]
 */

/** @type {ReturnType<typeof createStore<AppState>>} */
export const store = createStore({
  run: null,
  frames: [],
  currentFrame: null,
  metrics: [],
  connected: false,
  live: false,
  locale: 'en',
  theme: 'dark',
  scrubEpoch: -1,
  warnings: [],
  milestones: [],
  architecture: null,
});

/**
 * Append a new StoryFrame and update currentFrame (unless scrubbing).
 * @param {object} frame
 */
export function pushFrame(frame) {
  const s = store.get();
  const frames = [...s.frames, frame];
  const currentFrame = s.scrubEpoch === -1 ? frame : s.currentFrame;
  store.set({ frames, currentFrame });
}

/**
 * Push a milestone into the milestones list.
 * @param {object} milestone
 */
export function pushMilestone(milestone) {
  const s = store.get();
  store.set({ milestones: [...s.milestones, milestone] });
}

/**
 * Push a warning message (deduped by message text).
 * @param {string} message
 */
export function pushWarning(message) {
  const s = store.get();
  if (s.warnings.includes(message)) return;
  store.set({ warnings: [...s.warnings, message] });
}

/**
 * Seek to a specific epoch index (0-based into frames array).
 * Pass -1 to return to live/latest.
 * @param {number} idx
 */
export function scrubTo(idx) {
  const s = store.get();
  if (idx === -1) {
    store.set({ scrubEpoch: -1, currentFrame: s.frames.at(-1) ?? null });
  } else {
    const frame = s.frames[idx] ?? null;
    store.set({ scrubEpoch: idx, currentFrame: frame });
  }
}
