/**
 * Tests for src/store.js
 *
 * The `store` singleton is reset to its initial shape before every test so
 * each spec starts with a clean slate.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  createStore,
  store,
  pushFrame,
  pushMilestone,
  pushWarning,
  scrubTo,
  warningsInView,
} from '../store.js';

// ── helpers ───────────────────────────────────────────────────────────────────

const INITIAL_STATE = {
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
  warningKinds: new Map(),
  warningLog: [],
  milestones: [],
};

function resetStore() {
  store.set(INITIAL_STATE);
}

// ── createStore ───────────────────────────────────────────────────────────────

describe('createStore', () => {
  it('returns initial state from get()', () => {
    const s = createStore({ count: 0, label: 'hello' });
    expect(s.get()).toEqual({ count: 0, label: 'hello' });
  });

  it('set() merges patch into existing state', () => {
    const s = createStore({ a: 1, b: 2 });
    s.set({ b: 99 });
    expect(s.get()).toEqual({ a: 1, b: 99 });
  });

  it('set() does not mutate the previous state snapshot', () => {
    const s = createStore({ x: 1 });
    const before = s.get();
    s.set({ x: 2 });
    expect(before.x).toBe(1); // old snapshot unchanged
    expect(s.get().x).toBe(2);
  });

  it('subscribe() is called with new state on set()', () => {
    const s = createStore({ n: 0 });
    const calls = [];
    s.subscribe((state) => calls.push(state.n));
    s.set({ n: 5 });
    s.set({ n: 10 });
    expect(calls).toEqual([5, 10]);
  });

  it('multiple subscribers are all notified', () => {
    const s = createStore({ v: 0 });
    const a = vi.fn();
    const b = vi.fn();
    s.subscribe(a);
    s.subscribe(b);
    s.set({ v: 7 });
    expect(a).toHaveBeenCalledWith(expect.objectContaining({ v: 7 }));
    expect(b).toHaveBeenCalledWith(expect.objectContaining({ v: 7 }));
  });

  it('subscribe() returns an unsubscribe function', () => {
    const s = createStore({ n: 0 });
    const fn = vi.fn();
    const unsub = s.subscribe(fn);
    s.set({ n: 1 });
    expect(fn).toHaveBeenCalledTimes(1);
    unsub();
    s.set({ n: 2 });
    expect(fn).toHaveBeenCalledTimes(1); // no further calls after unsub
  });

  it('subscribe() does not call subscriber on initial get()', () => {
    const s = createStore({ n: 0 });
    const fn = vi.fn();
    s.subscribe(fn);
    expect(fn).not.toHaveBeenCalled(); // only called on set()
  });
});

// ── store singleton initial shape ─────────────────────────────────────────────

describe('store initial shape', () => {
  it('has all expected fields', () => {
    resetStore();
    const s = store.get();
    expect(s.run).toBeNull();
    expect(Array.isArray(s.frames)).toBe(true);
    expect(s.currentFrame).toBeNull();
    expect(Array.isArray(s.metrics)).toBe(true);
    expect(s.connected).toBe(false);
    expect(s.live).toBe(false);
    expect(s.locale).toBe('en');
    expect(s.theme).toBe('dark');
    expect(s.scrubEpoch).toBe(-1);
    expect(Array.isArray(s.warnings)).toBe(true);
    expect(Array.isArray(s.milestones)).toBe(true);
  });
});

// ── pushFrame ─────────────────────────────────────────────────────────────────

describe('pushFrame', () => {
  beforeEach(resetStore);

  it('appends frame to frames array', () => {
    const frame = { seq: 1, grade: 'B', phase: 'learning' };
    pushFrame(frame);
    expect(store.get().frames).toHaveLength(1);
    expect(store.get().frames[0]).toEqual(frame);
  });

  it('accumulates multiple frames in order', () => {
    pushFrame({ seq: 1 });
    pushFrame({ seq: 2 });
    pushFrame({ seq: 3 });
    expect(store.get().frames).toHaveLength(3);
    expect(store.get().frames.map((f) => f.seq)).toEqual([1, 2, 3]);
  });

  it('updates currentFrame when scrubEpoch is -1 (live mode)', () => {
    const frame = { seq: 1, grade: 'A' };
    pushFrame(frame);
    expect(store.get().currentFrame).toEqual(frame);
  });

  it('always updates currentFrame to latest when scrubEpoch=-1', () => {
    pushFrame({ seq: 1, grade: 'C' });
    pushFrame({ seq: 2, grade: 'B' });
    pushFrame({ seq: 3, grade: 'A' });
    expect(store.get().currentFrame?.grade).toBe('A');
  });

  it('does NOT update currentFrame when scrubbing (scrubEpoch ≥ 0)', () => {
    pushFrame({ seq: 1, grade: 'B' });
    scrubTo(0); // pin to first frame
    const pinnedFrame = store.get().currentFrame;
    pushFrame({ seq: 2, grade: 'A+' }); // new frame arrives during scrub
    expect(store.get().currentFrame).toEqual(pinnedFrame); // still pinned
    expect(store.get().frames).toHaveLength(2); // but frames array grew
  });

  it('does not mutate existing frames array reference', () => {
    const before = store.get().frames;
    pushFrame({ seq: 1 });
    expect(store.get().frames).not.toBe(before); // new array reference
  });
});

// ── pushMilestone ─────────────────────────────────────────────────────────────

describe('pushMilestone', () => {
  beforeEach(resetStore);

  it('appends milestone to milestones array', () => {
    const ms = { kind: 'best_val_accuracy', message: 'New best!' };
    pushMilestone(ms);
    expect(store.get().milestones).toHaveLength(1);
    expect(store.get().milestones[0]).toEqual(ms);
  });

  it('accumulates multiple milestones', () => {
    pushMilestone({ kind: 'first_metric' });
    pushMilestone({ kind: 'best_val_accuracy' });
    expect(store.get().milestones).toHaveLength(2);
  });

  it('does not mutate the previous milestones reference', () => {
    const before = store.get().milestones;
    pushMilestone({ kind: 'x' });
    expect(store.get().milestones).not.toBe(before);
  });
});

// ── pushWarning ───────────────────────────────────────────────────────────────

describe('pushWarning', () => {
  beforeEach(resetStore);

  it('appends a new warning message', () => {
    pushWarning('Overfitting detected');
    expect(store.get().warnings).toContain('Overfitting detected');
  });

  it('deduplicates the same message', () => {
    pushWarning('Plateau detected');
    pushWarning('Plateau detected');
    expect(store.get().warnings).toHaveLength(1);
  });

  it('allows different messages', () => {
    pushWarning('Warning A');
    pushWarning('Warning B');
    expect(store.get().warnings).toHaveLength(2);
  });

  it('does not mutate the previous warnings reference', () => {
    const before = store.get().warnings;
    pushWarning('new warning');
    expect(store.get().warnings).not.toBe(before);
  });
});

// ── a withdrawn overfit warning ───────────────────────────────────────────────
//
// A ResNet-18 on CIFAR-10 had one warm-up blip in validation loss at epoch 5,
// then set a new best at epoch 6 and kept falling. The engine withdraws its
// overfit warning with `overfit_cleared`; the dashboard must stop showing it.

describe('overfit_cleared', () => {
  beforeEach(resetStore);

  const overfit = { kind: 'overfit', epoch: 5, message: 'The model may be memorising.' };
  const cleared = { kind: 'overfit_cleared', epoch: 6, message: 'It was a blip.' };
  const lrDrop = { kind: 'lr_drop', epoch: 28, message: 'Learning rate decreased.' };

  it('withdraws the overfit warning and shows nothing in its place', () => {
    pushWarning(overfit);
    pushWarning(lrDrop);
    pushWarning(cleared);
    expect(store.get().warnings).toEqual(['Learning rate decreased.']);
  });

  it('works when the warnings ride on frames, as in a finished run', () => {
    pushFrame({ seq: 1, epoch: 5, warnings: [overfit] });
    expect(store.get().warnings).toEqual([overfit.message]);
    pushFrame({ seq: 2, epoch: 6, warnings: [cleared] });
    expect(store.get().warnings).toEqual([]);
  });

  it('lets the warning come back if the run overfits again', () => {
    pushWarning(overfit);
    pushWarning(cleared);
    pushWarning({ ...overfit, epoch: 20 });
    expect(store.get().warnings).toEqual([overfit.message]);
  });

  it('a message named __proto__ is data, not a prototype key', () => {
    // CodeQL js/remote-property-injection: message text comes from log files.
    pushWarning({ kind: 'overfit', message: '__proto__' });
    pushWarning({ kind: 'plateau', message: 'constructor' });
    expect(store.get().warnings).toEqual(['__proto__', 'constructor']);
    expect(({}).polluted).toBeUndefined();
    expect(Object.getPrototypeOf(store.get().warningKinds)).toBe(Map.prototype);
    pushWarning({ kind: 'overfit_cleared', message: 'x' });
    expect(store.get().warnings).toEqual(['constructor']);
  });

  it('leaves a plain string warning alone', () => {
    pushWarning('Plateau detected');
    pushWarning(cleared);
    expect(store.get().warnings).toEqual(['Plateau detected']);
  });
});

// ── a withdrawn plateau warning ───────────────────────────────────────────────
//
// A real Keras run moved less than 1% over five epochs mid-way, then climbed
// to its best at the last one. The banner still said progress had slowed,
// beside a grade card saying "still improving at the last reading".

describe('plateau_cleared', () => {
  beforeEach(resetStore);

  const plateau = { kind: 'plateau', epoch: 12, message: 'Progress has slowed.' };
  const cleared = { kind: 'plateau_cleared', epoch: 15, message: 'Moving again.' };
  const overfit = { kind: 'overfit', epoch: 9, message: 'The model may be memorising.' };

  it('withdraws the plateau warning and nothing else', () => {
    pushWarning(overfit);
    pushWarning(plateau);
    pushWarning(cleared);
    expect(store.get().warnings).toEqual([overfit.message]);
  });

  it('works when the warnings ride on frames, as in a finished run', () => {
    pushFrame({ seq: 1, epoch: 12, warnings: [plateau] });
    expect(store.get().warnings).toEqual([plateau.message]);
    pushFrame({ seq: 2, epoch: 15, warnings: [cleared] });
    expect(store.get().warnings).toEqual([]);
  });

  it('lets the warning come back if the run flattens again', () => {
    pushWarning(plateau);
    pushWarning(cleared);
    pushWarning({ ...plateau, epoch: 19 });
    expect(store.get().warnings).toEqual([plateau.message]);
  });

  it('an overfit withdrawal does not touch a plateau', () => {
    pushWarning(plateau);
    pushWarning({ kind: 'overfit_cleared', epoch: 13, message: 'It was a blip.' });
    expect(store.get().warnings).toEqual([plateau.message]);
  });

  it('a withdrawal with nothing to withdraw is never shown', () => {
    pushWarning(cleared);
    expect(store.get().warnings).toEqual([]);
  });
});

// ── warnings follow the frame in view ─────────────────────────────────────────
//
// The README's GIF steps the scrubber through the Keras demo. Every frame was
// headed by the run's *final* warning: "moved less than 1% over the last 5
// readings" over epoch 1, and over epochs where it had been withdrawn.

describe('warningsInView', () => {
  beforeEach(resetStore);

  const plateau = { kind: 'plateau', epoch: 3, message: 'Progress has slowed.' };
  const cleared = { kind: 'plateau_cleared', epoch: 4, message: 'Moving again.' };
  const shown = () => warningsInView(store.get()).warnings;

  function finishedRun() {
    pushFrame({ seq: 1, epoch: 1 });
    pushFrame({ seq: 2, epoch: 2 });
    pushFrame({ seq: 3, epoch: 3, warnings: [plateau] });
    pushFrame({ seq: 4, epoch: 4, warnings: [cleared] });
    pushFrame({ seq: 5, epoch: 5 });
    pushFrame({ seq: 6, epoch: 6, warnings: [{ ...plateau, epoch: 6 }] });
  }

  it('is the standing warnings at the latest frame', () => {
    finishedRun();
    expect(shown()).toEqual([plateau.message]);
    expect(shown()).toEqual(store.get().warnings);
  });

  it('shows nothing before the warning fired', () => {
    finishedRun();
    scrubTo(0);
    expect(shown()).toEqual([]);
    scrubTo(1);
    expect(shown()).toEqual([]);
  });

  it('shows the warning at the frame it fired on', () => {
    finishedRun();
    scrubTo(2);
    expect(shown()).toEqual([plateau.message]);
  });

  it('shows nothing where it had been withdrawn', () => {
    finishedRun();
    scrubTo(3);
    expect(shown()).toEqual([]);
    scrubTo(4);
    expect(shown()).toEqual([]);
  });

  it('returning to the latest frame shows what stands now', () => {
    finishedRun();
    scrubTo(0);
    scrubTo(-1);
    expect(shown()).toEqual([plateau.message]);
  });

  it('carries the kinds, so a learning-rate drop can still be told apart', () => {
    pushFrame({ seq: 1, epoch: 1, warnings: [{ kind: 'lr_drop', epoch: 1, message: 'lr fell' }] });
    pushFrame({ seq: 2, epoch: 2 });
    scrubTo(0);
    expect(warningsInView(store.get()).warningKinds.get('lr fell')).toBe('lr_drop');
  });

  it('places a warning that arrived by itself by its epoch', () => {
    // The extension sends its engine's warnings beside the frames, not on them.
    for (let e = 1; e <= 5; e++) pushFrame({ seq: e, epoch: e });
    pushWarning(plateau);
    pushWarning(cleared);
    scrubTo(1);
    expect(shown()).toEqual([]);
    scrubTo(2);
    expect(shown()).toEqual([plateau.message]);
    scrubTo(3);
    expect(shown()).toEqual([]);
  });

  it('keeps a warning it cannot place', () => {
    pushFrame({ seq: 1, epoch: 1 });
    pushFrame({ seq: 2, epoch: 2 });
    pushWarning('no epoch on this one');
    scrubTo(0);
    expect(shown()).toEqual(['no epoch on this one']);
  });
});

// ── scrubTo ───────────────────────────────────────────────────────────────────

describe('scrubTo', () => {
  beforeEach(() => {
    resetStore();
    pushFrame({ seq: 1, grade: 'C' });
    pushFrame({ seq: 2, grade: 'B' });
    pushFrame({ seq: 3, grade: 'A' });
  });

  it('seeks to a specific frame by index', () => {
    scrubTo(0);
    expect(store.get().currentFrame?.grade).toBe('C');
    expect(store.get().scrubEpoch).toBe(0);
  });

  it('seeks to middle frame', () => {
    scrubTo(1);
    expect(store.get().currentFrame?.grade).toBe('B');
  });

  it('scrubTo(-1) returns to live mode and shows latest frame', () => {
    scrubTo(0); // first pin to index 0
    scrubTo(-1); // then return to live
    expect(store.get().scrubEpoch).toBe(-1);
    expect(store.get().currentFrame?.grade).toBe('A'); // latest
  });

  it('scrubTo(-1) sets currentFrame to null when frames is empty', () => {
    resetStore(); // empty frames
    scrubTo(-1);
    expect(store.get().currentFrame).toBeNull();
  });

  it('scrubTo with out-of-range index sets currentFrame to null', () => {
    scrubTo(99);
    expect(store.get().currentFrame).toBeNull();
  });
});

describe('pushFrame de-duplication', () => {
  it('ignores a frame whose seq is already held', async () => {
    // A replayed snapshot (repeated init, reconnect with last_seq) used to
    // append the whole run on top of itself, so the phase journey drew every
    // phase twice with the same epoch ranges.
    const { store, pushFrame } = await import('../store.js');
    store.set({ frames: [], currentFrame: null, scrubEpoch: -1 });

    pushFrame({ seq: 1, epoch: 1, phase: 'awakening', grade: 'F' });
    pushFrame({ seq: 2, epoch: 2, phase: 'learning', grade: 'B' });
    pushFrame({ seq: 1, epoch: 1, phase: 'awakening', grade: 'F' }); // replay
    pushFrame({ seq: 2, epoch: 2, phase: 'learning', grade: 'B' }); // replay

    expect(store.get().frames.length).toBe(2);
    expect(store.get().frames.map((f) => f.seq)).toEqual([1, 2]);
  });

  it('still appends frames that have no seq', async () => {
    const { store, pushFrame } = await import('../store.js');
    store.set({ frames: [], currentFrame: null, scrubEpoch: -1 });
    pushFrame({ epoch: 1 });
    pushFrame({ epoch: 2 });
    expect(store.get().frames.length).toBe(2);
  });
});
