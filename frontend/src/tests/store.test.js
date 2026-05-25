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
