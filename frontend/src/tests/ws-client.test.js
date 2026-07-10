/**
 * Tests for src/ws-client.js
 *
 * WebSocket, location, and timers are all mocked / faked so tests are
 * deterministic and do not require a running server.
 *
 * Strategy:
 *  - vi.useFakeTimers() to control setTimeout / clearTimeout.
 *  - A lightweight MockWebSocket class to stub the browser WebSocket API.
 *  - vi.resetModules() + dynamic import in each suite so module-level state
 *    (_ws, _lastSeq, etc.) starts fresh.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── MockWebSocket ─────────────────────────────────────────────────────────────

class MockWebSocket {
  /** @type {MockWebSocket[]} */
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    MockWebSocket.instances.push(this);
  }

  /** Simulate the server accepting the connection. */
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({ target: this });
  }

  /** Simulate a message arriving from the server. */
  simulateMessage(data) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }

  /** Simulate the connection closing (e.g. server drop). */
  simulateClose(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, target: this });
  }

  simulateError() {
    this.onerror?.({ target: this });
    this.simulateClose();
  }

  close() {
    if (this.readyState !== MockWebSocket.CLOSED) {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.({ code: 1000, target: this });
    }
  }

  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static reset() {
    MockWebSocket.instances = [];
  }

  static get latest() {
    return MockWebSocket.instances.at(-1) ?? null;
  }
}

// ── Test suite helpers ────────────────────────────────────────────────────────

async function loadClient() {
  vi.resetModules();
  return import('../ws-client.js');
}

function setupGlobals() {
  globalThis.WebSocket = MockWebSocket;
  globalThis.location = { protocol: 'http:', host: 'localhost:7860' };
}

// ── connect / disconnect basics ───────────────────────────────────────────────

describe('connect()', () => {
  let mod, storeModule;

  beforeEach(async () => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    setupGlobals();
    vi.resetModules();
    storeModule = await import('../store.js');
    storeModule.store.set({
      run: null, frames: [], currentFrame: null, metrics: [],
      connected: false, live: false, locale: 'en', theme: 'dark',
      scrubEpoch: -1, warnings: [], milestones: [],
    });
    mod = await import('../ws-client.js');
  });

  afterEach(() => {
    vi.useRealTimers();
    mod.disconnect();
  });

  it('creates a WebSocket for the given run id', () => {
    mod.connect('run-abc');
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.latest.url).toContain('run-abc');
  });

  it('WebSocket URL uses ws:// for http:', () => {
    mod.connect('run-1');
    expect(MockWebSocket.latest.url).toMatch(/^ws:\/\//);
  });

  it('WebSocket URL uses wss:// for https:', () => {
    globalThis.location = { protocol: 'https:', host: 'example.com' };
    mod.connect('run-2');
    expect(MockWebSocket.latest.url).toMatch(/^wss:\/\//);
  });

  it('WebSocket URL contains last_seq param', () => {
    mod.connect('run-3', 5);
    expect(MockWebSocket.latest.url).toContain('last_seq=5');
  });

  it('sets connected=true when socket opens', () => {
    mod.connect('run-open');
    MockWebSocket.latest.simulateOpen();
    expect(storeModule.store.get().connected).toBe(true);
  });

  it('sets connected=false when socket closes', () => {
    mod.connect('run-close');
    MockWebSocket.latest.simulateOpen();
    MockWebSocket.latest.simulateClose();
    expect(storeModule.store.get().connected).toBe(false);
  });
});

// ── disconnect() ─────────────────────────────────────────────────────────────

describe('disconnect()', () => {
  let mod, storeModule;

  beforeEach(async () => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    setupGlobals();
    vi.resetModules();
    storeModule = await import('../store.js');
    storeModule.store.set({
      run: null, frames: [], currentFrame: null, metrics: [],
      connected: false, live: false, locale: 'en', theme: 'dark',
      scrubEpoch: -1, warnings: [], milestones: [],
    });
    mod = await import('../ws-client.js');
  });

  afterEach(() => vi.useRealTimers());

  it('sets connected=false', () => {
    mod.connect('run-dc');
    MockWebSocket.latest.simulateOpen();
    mod.disconnect();
    expect(storeModule.store.get().connected).toBe(false);
  });

  it('prevents reconnect after disconnect', () => {
    mod.connect('run-no-reconnect');
    MockWebSocket.latest.simulateOpen();
    mod.disconnect();
    const countBefore = MockWebSocket.instances.length;
    vi.runAllTimers(); // no timers should fire
    expect(MockWebSocket.instances.length).toBe(countBefore);
  });

  it('is idempotent — calling disconnect() twice does not throw', () => {
    mod.connect('run-idem');
    mod.disconnect();
    expect(() => mod.disconnect()).not.toThrow();
  });
});

// ── message handling ──────────────────────────────────────────────────────────

describe('message handling', () => {
  let mod, storeModule;

  beforeEach(async () => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    setupGlobals();
    vi.resetModules();
    storeModule = await import('../store.js');
    storeModule.store.set({
      run: null, frames: [], currentFrame: null, metrics: [],
      connected: false, live: false, locale: 'en', theme: 'dark',
      scrubEpoch: -1, warnings: [], milestones: [],
    });
    mod = await import('../ws-client.js');
    mod.connect('msg-run');
    MockWebSocket.latest.simulateOpen();
  });

  afterEach(() => {
    vi.useRealTimers();
    mod.disconnect();
  });

  it('ping message: no state change', () => {
    const before = storeModule.store.get();
    MockWebSocket.latest.simulateMessage({ type: 'ping', seq: 1 });
    expect(storeModule.store.get()).toEqual(before);
  });

  it('story_frame: frame is pushed to store', () => {
    MockWebSocket.latest.simulateMessage({
      type: 'story_frame',
      seq: 1,
      payload: { grade: 'B', phase: 'learning', primary_metric_value: 0.75 },
    });
    expect(storeModule.store.get().frames).toHaveLength(1);
    expect(storeModule.store.get().frames[0].grade).toBe('B');
  });

  it('story_frame: duplicate seq is ignored', () => {
    const msg = { type: 'story_frame', seq: 1, payload: { grade: 'B' } };
    MockWebSocket.latest.simulateMessage(msg);
    MockWebSocket.latest.simulateMessage(msg); // same seq again
    expect(storeModule.store.get().frames).toHaveLength(1);
  });

  it('story_frame: lower seq than already seen is ignored', () => {
    MockWebSocket.latest.simulateMessage({ type: 'story_frame', seq: 5, payload: { grade: 'A' } });
    MockWebSocket.latest.simulateMessage({ type: 'story_frame', seq: 3, payload: { grade: 'F' } });
    expect(storeModule.store.get().frames).toHaveLength(1);
    expect(storeModule.store.get().frames[0].grade).toBe('A');
  });

  it('milestone: appended to milestones', () => {
    MockWebSocket.latest.simulateMessage({
      type: 'milestone',
      seq: 2,
      payload: { kind: 'best_val_accuracy', message: 'New best!' },
    });
    expect(storeModule.store.get().milestones).toHaveLength(1);
    expect(storeModule.store.get().milestones[0].kind).toBe('best_val_accuracy');
  });

  it('milestone: no payload → nothing pushed', () => {
    MockWebSocket.latest.simulateMessage({ type: 'milestone', seq: 3 });
    expect(storeModule.store.get().milestones).toHaveLength(0);
  });

  it('warning: message pushed to warnings', () => {
    MockWebSocket.latest.simulateMessage({
      type: 'warning',
      seq: 4,
      payload: { message: 'Overfitting detected' },
    });
    expect(storeModule.store.get().warnings).toContain('Overfitting detected');
  });

  it('activations: layer map routed into store.activations', () => {
    const layers = { 'fc1': { mag: 0.42, dead: 0.13 }, 'fc2': { mag: 0.9, dead: 0 } };
    MockWebSocket.latest.simulateMessage({ type: 'activations', seq: -1, payload: { layers } });
    expect(storeModule.store.get().activations).toEqual(layers);
  });

  it('activations: latest snapshot wins (not seq-gated)', () => {
    MockWebSocket.latest.simulateMessage({
      type: 'activations', seq: -1, payload: { layers: { fc1: { mag: 0.1, dead: 0 } } },
    });
    MockWebSocket.latest.simulateMessage({
      type: 'activations', seq: -1, payload: { layers: { fc1: { mag: 0.8, dead: 0 } } },
    });
    expect(storeModule.store.get().activations.fc1.mag).toBe(0.8);
  });

  it('activations: no layers payload → no change', () => {
    MockWebSocket.latest.simulateMessage({ type: 'activations', seq: -1, payload: {} });
    expect(storeModule.store.get().activations).toBe(null);
  });

  it('complete: sets live=false and disconnects', () => {
    MockWebSocket.latest.simulateMessage({ type: 'complete', seq: 99 });
    expect(storeModule.store.get().live).toBe(false);
    expect(storeModule.store.get().connected).toBe(false);
  });

  it('unknown type: silently ignored', () => {
    expect(() => {
      MockWebSocket.latest.simulateMessage({ type: 'unknown_type', seq: 1 });
    }).not.toThrow();
  });

  it('malformed JSON: silently ignored', () => {
    expect(() => {
      MockWebSocket.latest.simulateMessage('not valid { json !!!');
    }).not.toThrow();
  });
});

// ── reconnect / backoff ───────────────────────────────────────────────────────

describe('reconnect backoff', () => {
  let mod, storeModule;

  beforeEach(async () => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    setupGlobals();
    vi.resetModules();
    storeModule = await import('../store.js');
    storeModule.store.set({
      run: null, frames: [], currentFrame: null, metrics: [],
      connected: false, live: false, locale: 'en', theme: 'dark',
      scrubEpoch: -1, warnings: [], milestones: [],
    });
    mod = await import('../ws-client.js');
  });

  afterEach(() => {
    vi.useRealTimers();
    mod.disconnect();
  });

  it('reconnects after a close', () => {
    mod.connect('backoff-run');
    MockWebSocket.latest.simulateOpen();
    MockWebSocket.latest.simulateClose();
    vi.runAllTimers();
    expect(MockWebSocket.instances.length).toBeGreaterThan(1);
  });

  it('new socket URL includes updated last_seq after replay', () => {
    mod.connect('seq-run', -1);
    MockWebSocket.latest.simulateOpen();
    MockWebSocket.latest.simulateMessage({
      type: 'story_frame', seq: 7, payload: { grade: 'B' },
    });
    MockWebSocket.latest.simulateClose();
    vi.runAllTimers();
    // second socket should have last_seq=7
    expect(MockWebSocket.latest.url).toContain('last_seq=7');
  });

  it('backoff resets to initial after successful open', () => {
    mod.connect('reset-run');
    const first = MockWebSocket.latest;
    first.simulateOpen(); // open → backoff resets
    first.simulateClose();
    vi.runAllTimers(); // fires 1s timer → opens second socket
    const second = MockWebSocket.latest;
    second.simulateOpen();  // open → backoff resets again
    second.simulateClose();
    vi.runAllTimers(); // fires 1s timer → opens third socket
    expect(MockWebSocket.instances.length).toBe(3);
  });
});

// ── heartbeat timeout ─────────────────────────────────────────────────────────

describe('heartbeat timeout', () => {
  let mod, storeModule;

  beforeEach(async () => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    setupGlobals();
    vi.resetModules();
    storeModule = await import('../store.js');
    storeModule.store.set({
      run: null, frames: [], currentFrame: null, metrics: [],
      connected: false, live: false, locale: 'en', theme: 'dark',
      scrubEpoch: -1, warnings: [], milestones: [],
    });
    mod = await import('../ws-client.js');
  });

  afterEach(() => {
    vi.useRealTimers();
    mod.disconnect();
  });

  it('closes socket after 45s of silence', () => {
    mod.connect('hb-run');
    MockWebSocket.latest.simulateOpen();
    const ws = MockWebSocket.latest;
    vi.advanceTimersByTime(45_001);
    // After 45s the heartbeat timer closes the socket
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
  });

  it('resets heartbeat timer on each message', () => {
    mod.connect('hb-run2');
    MockWebSocket.latest.simulateOpen();
    const ws = MockWebSocket.latest;
    // Advance 40s, then deliver a message
    vi.advanceTimersByTime(40_000);
    ws.simulateMessage({ type: 'ping', seq: 0 });
    // 45s more should not close (timer was reset to 45s from the message)
    vi.advanceTimersByTime(40_000);
    expect(ws.readyState).toBe(MockWebSocket.OPEN);
  });
});
