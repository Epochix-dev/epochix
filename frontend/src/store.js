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
 * @property {Object<string,{mag:number,dead:number,grad?:number}>|null} activations - Real per-layer activation magnitudes captured from the model (null = none / schematic)
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
  // message -> kind for each shown warning, so a later `<kind>_cleared` knows
  // which messages it withdraws. A Map, not an object: the message text comes
  // from log files, and a message named `__proto__` must not become a key.
  warningKinds: new Map(),
  // Every warning received, in order, with the index of the frame it rode on
  // (null for one that arrived by itself). `warnings` is what stands at the
  // latest frame; this is what lets a scrubbed view show what stood *then*.
  warningLog: [],
  milestones: [],
  architecture: null,
  activations: null,
  // run.config.cross_validation: every setting's fold readings, or null.
  crossValidation: null,
});

/**
 * Append a new StoryFrame and update currentFrame (unless scrubbing).
 * @param {object} frame
 */
export function pushFrame(frame) {
  const s = store.get();
  // A replayed snapshot can redeliver frames we already have (reconnect with
  // last_seq, a repeated init). Appending them duplicated the whole run.
  if (frame?.seq != null && s.frames.some((f) => f.seq === frame.seq)) return;
  const frames = [...s.frames, frame];
  const currentFrame = s.scrubEpoch === -1 ? frame : s.currentFrame;

  // Warnings ride ON the frame. They were only ever read from the live
  // `warning` SSE message, so opening a finished run — or any HTML export —
  // showed none of them: the engine had detected the overfitting, stored it on
  // the frame, and the dashboard displayed nothing. Taking them from the frame
  // covers the snapshot, the export and the live stream in one place.
  const carried = frame?.warnings ?? [];
  const at = frames.length - 1;
  store.set({
    frames,
    currentFrame,
    ..._withWarnings(s, carried),
    ...(carried.length
      ? { warningLog: [...(s.warningLog ?? []), ...carried.map((warning) => ({ warning, frame: at }))] }
      : {}),
  });
}

const CLEARED = '_cleared';

/**
 * The warning list after `incoming` arrives, or {} when nothing changed.
 *
 * A `<kind>_cleared` warning is not shown: it withdraws the `<kind>` warning
 * before it. The engine sends `overfit_cleared` when validation loss beats its
 * best from before the rise — a ResNet-18 run's warm-up blip at epoch 5
 * otherwise told the reader, at epoch 30, to "stop at the best validation
 * epoch", which was epoch 30 — and `plateau_cleared` when the metric has moved
 * more than 1% over its last five readings again: a Keras run that flattened
 * mid-way otherwise ended on "progress has slowed" beside "still improving".
 * @param {{warnings: string[], warningKinds?: Map<string,string>}} s
 * @param {Array<string|{kind?: string, message?: string}>} incoming
 */
function _withWarnings(s, incoming) {
  let warnings = s.warnings;
  let kinds = s.warningKinds instanceof Map ? s.warningKinds : new Map();
  let changed = false;
  for (const w of incoming) {
    const message = typeof w === 'string' ? w : w?.message;
    const kind = typeof w === 'string' ? undefined : w?.kind;
    if (typeof kind === 'string' && kind.endsWith(CLEARED)) {
      const withdrawn = kind.slice(0, -CLEARED.length);
      const kept = warnings.filter((m) => kinds.get(m) !== withdrawn);
      if (kept.length !== warnings.length) {
        kinds = new Map([...kinds].filter(([, k]) => k !== withdrawn));
        warnings = kept;
        changed = true;
      }
      continue;
    }
    if (message && !warnings.includes(message)) {
      warnings = [...warnings, message];
      if (kind) kinds = new Map(kinds).set(message, kind);
      changed = true;
    }
  }
  return changed ? { warnings, warningKinds: kinds } : {};
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
 * Push a warning (deduped by message text). Pass the whole warning, not only
 * its message: its kind is what lets a `<kind>_cleared` withdraw it.
 * @param {string|{kind?: string, message?: string}} warning
 */
export function pushWarning(warning) {
  const s = store.get();
  store.set({
    ..._withWarnings(s, [warning]),
    warningLog: [...(s.warningLog ?? []), { warning, frame: null }],
  });
}

/**
 * The warnings that stand at the frame being viewed.
 *
 * At the latest frame that is `warnings`. Scrubbed back, it is what stood
 * then: a warning says "over the last 5 readings", and showing the run's final
 * warnings over epoch 3 put "progress has slowed" above a model that had
 * barely started — and showed a warning at epochs where it had been withdrawn.
 * A warning that did not ride on a frame is placed by its epoch; one with no
 * epoch cannot be placed, and stays.
 * @param {AppState} s
 * @returns {{warnings: string[], warningKinds: Map<string,string>}}
 */
export function warningsInView(s) {
  const latest = {
    warnings: s.warnings ?? [],
    warningKinds: s.warningKinds instanceof Map ? s.warningKinds : new Map(),
  };
  const viewed = s.scrubEpoch >= 0 ? s.frames?.[s.scrubEpoch] : null;
  if (!viewed || !Array.isArray(s.warningLog) || s.warningLog.length === 0) return latest;
  const reached = ({ warning, frame }) => {
    if (frame != null) return frame <= s.scrubEpoch;
    const at = typeof warning === 'string' ? null : warning?.epoch;
    return at == null || viewed.epoch == null || at <= viewed.epoch;
  };
  const then = _withWarnings(
    { warnings: [], warningKinds: new Map() },
    s.warningLog.filter(reached).map((entry) => entry.warning),
  );
  return { warnings: then.warnings ?? [], warningKinds: then.warningKinds ?? new Map() };
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
