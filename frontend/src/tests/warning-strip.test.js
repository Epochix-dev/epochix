/**
 * The engine's warnings must reach the screen.
 *
 * A Warning is emitted for overfitting, a plateau, divergence and a
 * learning-rate drop. `sse-client` received them and `store.warnings` held
 * them — and nothing rendered them, so a diverging run computed the warning,
 * transmitted it, stored it, and told the user nothing. That is the failure
 * this project exists to avoid, in its own dashboard.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { WarningStrip } from '../visualizations/WarningStrip.js';

function fakeStore(initial = []) {
  let state = { warnings: initial };
  const subs = [];
  return {
    get: () => state,
    set: (patch) => { state = { ...state, ...patch }; subs.forEach((f) => f(state)); },
    subscribe: (fn) => { subs.push(fn); return () => subs.splice(subs.indexOf(fn), 1); },
  };
}

describe('WarningStrip', () => {
  let el;
  beforeEach(() => {
    document.body.innerHTML = '<div id="warning-strip" hidden></div>';
    el = document.getElementById('warning-strip');
  });

  it('shows a warning the store already holds', () => {
    const store = fakeStore(['Validation loss is rising while training loss falls.']);
    new WarningStrip(el).mount(store);
    expect(el.hidden).toBe(false);
    expect(el.textContent).toContain('Validation loss is rising');
  });

  it('appears when a warning arrives later', () => {
    const store = fakeStore([]);
    new WarningStrip(el).mount(store);
    expect(el.hidden).toBe(true);
    store.set({ warnings: ['Loss diverged.'] });
    expect(el.hidden).toBe(false);
    expect(el.textContent).toContain('Loss diverged');
  });

  it('takes no space when there is nothing wrong', () => {
    const store = fakeStore([]);
    new WarningStrip(el).mount(store);
    expect(el.hidden).toBe(true);
    expect(el.innerHTML).toBe('');
  });

  it('shows every warning, not just the newest', () => {
    const store = fakeStore(['first', 'second', 'third']);
    new WarningStrip(el).mount(store);
    expect(el.querySelectorAll('.warn-item')).toHaveLength(3);
  });

  it('escapes warning text', () => {
    // Warning messages carry metric names, which come from log files.
    const store = fakeStore(['<img src=x onerror=alert(1)>']);
    new WarningStrip(el).mount(store);
    expect(el.querySelector('img')).toBeNull();
    expect(el.textContent).toContain('<img src=x');
  });

  it('does not rebuild the DOM for an unchanged list', () => {
    const store = fakeStore(['steady']);
    new WarningStrip(el).mount(store);
    const first = el.querySelector('.warn-item');
    store.set({ warnings: ['steady'] });
    // Re-rendering identical content would restart the CSS transition and
    // make a persistent warning flicker on every frame.
    expect(el.querySelector('.warn-item')).toBe(first);
  });
});

describe('warnings travel on the frame, not only on the live message', () => {
  it('a snapshot frame surfaces its warnings', async () => {
    // Opening a finished run — or any HTML export — replays frames and never
    // sees a live `warning` message. The warning is ON the frame; reading it
    // only from the SSE event meant a completed overfitting run displayed
    // nothing at all.
    const { store, pushFrame } = await import('../store.js');
    pushFrame({ seq: 900, warnings: [{ kind: 'overfit', message: 'memorising, not learning' }] });
    expect(store.get().warnings).toContain('memorising, not learning');
  });

  it('does not repeat a warning carried by several frames', async () => {
    const { store, pushFrame } = await import('../store.js');
    const before = store.get().warnings.length;
    pushFrame({ seq: 901, warnings: [{ kind: 'plateau', message: 'flat for a while' }] });
    pushFrame({ seq: 902, warnings: [{ kind: 'plateau', message: 'flat for a while' }] });
    expect(store.get().warnings.length).toBe(before + 1);
  });

  it('accepts a bare string as well as a Warning object', async () => {
    const { store, pushFrame } = await import('../store.js');
    pushFrame({ seq: 903, warnings: ['plain string warning'] });
    expect(store.get().warnings).toContain('plain string warning');
  });

  it('a frame with no warnings changes nothing', async () => {
    const { store, pushFrame } = await import('../store.js');
    const before = [...store.get().warnings];
    pushFrame({ seq: 904 });
    expect(store.get().warnings).toEqual(before);
  });
});
