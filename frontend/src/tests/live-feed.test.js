/**
 * The live feed over both transports: the WebSocket client and the SSE
 * fallback apply one run's messages through one handler (live-message.js),
 * and the WebSocket client hands over to SSE when it cannot open at all.
 *
 * The message sequence is the shape a real `epochix --live` run sends: a
 * frame's milestones carry the frame's own seq and follow it, and the run's
 * last milestones come after its last frame.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

class MockWebSocket {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.onopen = this.onmessage = this.onerror = this.onclose = null;
    this.closed = false;
    MockWebSocket.instances.push(this);
  }
  open() { this.onopen?.({}); }
  send(msg) { this.onmessage?.({ data: JSON.stringify(msg) }); }
  /** The upgrade refused: the handshake fails and the socket closes. */
  refuse() { this.onerror?.({}); this.closed = true; this.onclose?.({ code: 1006 }); }
  close() {
    if (!this.closed) { this.closed = true; this.onclose?.({ code: 1000 }); }
  }
  static get latest() { return MockWebSocket.instances.at(-1) ?? null; }
}

class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.onopen = this.onmessage = this.onerror = null;
    this.closed = false;
    MockEventSource.instances.push(this);
  }
  open() { this.onopen?.({}); }
  send(msg) { this.onmessage?.({ data: JSON.stringify(msg) }); }
  close() { this.closed = true; }
  static get latest() { return MockEventSource.instances.at(-1) ?? null; }
}

const RUN = '01RUN';
const frame = (seq, epoch) => ({
  v: 1, type: 'story_frame', run_id: RUN, seq,
  payload: { run_id: RUN, seq, epoch, grade: 'B', narrative: `epoch ${epoch}` },
});
const milestone = (seq, kind, epoch) => ({
  v: 1, type: 'milestone', run_id: RUN, seq,
  payload: { run_id: RUN, seq, kind, epoch, message: `${kind} at ${epoch}` },
});
const RUN_MESSAGES = [
  frame(3, 3),
  frame(4, 4),
  milestone(4, 'best_val_accuracy', 4),
  frame(5, 5),
  milestone(5, 'best_val_accuracy', 5),
  milestone(6, 'training_complete', 5),
  { v: 1, type: 'complete', run_id: RUN, seq: 5, payload: { final_grade: 'B+' } },
];

let storeModule;

async function freshModules() {
  vi.resetModules();
  storeModule = await import('../store.js');
  storeModule.store.set({
    run: { id: RUN, finished_at: null }, frames: [], currentFrame: null, metrics: [],
    connected: false, live: true, locale: 'en', theme: 'dark',
    scrubEpoch: -1, warnings: [], milestones: [], architecture: null,
    activations: null, crossValidation: null,
  });
  return {
    ws: await import('../ws-client.js'),
    sse: await import('../sse-client.js'),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  MockWebSocket.instances = [];
  MockEventSource.instances = [];
  globalThis.WebSocket = MockWebSocket;
  globalThis.EventSource = MockEventSource;
  globalThis.location = { protocol: 'http:', host: 'localhost:7860' };
});

afterEach(() => {
  vi.useRealTimers();
});

// Each transport, connected and open, and how to deliver a message on it.
const TRANSPORTS = {
  websocket: async () => {
    const mods = await freshModules();
    mods.ws.connect(RUN, 2);
    MockWebSocket.latest.open();
    return { deliver: (m) => MockWebSocket.latest.send(m), mods };
  },
  sse: async () => {
    const mods = await freshModules();
    mods.sse.connectSSE(RUN, 2);
    MockEventSource.latest.open();
    return { deliver: (m) => MockEventSource.latest.send(m), mods };
  },
};

describe.each(Object.keys(TRANSPORTS))('a live run over %s', (name) => {
  it('keeps every milestone, including those that share their frame\'s seq', async () => {
    const { deliver } = await TRANSPORTS[name]();
    for (const m of RUN_MESSAGES) deliver(m);
    const s = storeModule.store.get();
    expect(s.frames.map((f) => f.seq)).toEqual([3, 4, 5]);
    expect(s.milestones.map((m) => `${m.seq}:${m.kind}`)).toEqual([
      '4:best_val_accuracy',
      '5:best_val_accuracy',
      '6:training_complete',
    ]);
  });

  it('applies a replayed message once', async () => {
    const { deliver } = await TRANSPORTS[name]();
    for (const m of RUN_MESSAGES.slice(0, 3)) deliver(m);
    for (const m of RUN_MESSAGES.slice(0, 3)) deliver(m); // a reconnect's replay
    const s = storeModule.store.get();
    expect(s.frames.map((f) => f.seq)).toEqual([3, 4]);
    expect(s.milestones).toHaveLength(1);
  });

  it('ends the run on complete and stops listening', async () => {
    const { deliver } = await TRANSPORTS[name]();
    for (const m of RUN_MESSAGES) deliver(m);
    const s = storeModule.store.get();
    expect(s.live).toBe(false);
    expect(s.run.final_grade).toBe('B+');
    if (name === 'sse') expect(MockEventSource.latest.closed).toBe(true);
    else expect(MockWebSocket.latest.closed).toBe(true);
  });

  it('takes the architecture, activations and folds the server sends', async () => {
    const { deliver } = await TRANSPORTS[name]();
    const layers = [{ name: 'fc1', layer_type: 'Linear', params: 10 }];
    deliver({ v: 1, type: 'architecture', run_id: RUN, seq: -1, payload: { architecture: layers } });
    deliver({ v: 1, type: 'activations', run_id: RUN, seq: -1, payload: { layers: { fc1: { mean_abs: 0.3 } } } });
    const folds = { folds: [{ fold: 0, score: 0.8 }] };
    deliver({ v: 1, type: 'complete', run_id: RUN, seq: 5, payload: { cross_validation: folds } });
    const s = storeModule.store.get();
    expect(s.architecture).toEqual(layers);
    expect(s.activations).toEqual({ fc1: { mean_abs: 0.3 } });
    expect(s.crossValidation).toEqual(folds);
  });
});

describe('the WebSocket client hands over to SSE', () => {
  it('when the upgrade is refused twice, with the last seq it had', async () => {
    const { ws } = await freshModules();
    const handOver = vi.fn();
    ws.connect(RUN, 7, { onUnavailable: handOver });
    MockWebSocket.latest.refuse();
    expect(handOver).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000); // the first reconnect
    expect(MockWebSocket.instances).toHaveLength(2);
    MockWebSocket.latest.refuse();
    expect(handOver).toHaveBeenCalledOnce();
    expect(handOver).toHaveBeenCalledWith(7);
    vi.advanceTimersByTime(60_000);
    expect(MockWebSocket.instances).toHaveLength(2); // and it stops trying
  });

  it('not when a socket has opened: that is a dropped connection, not a refusal', async () => {
    const { ws } = await freshModules();
    const handOver = vi.fn();
    ws.connect(RUN, 2, { onUnavailable: handOver });
    MockWebSocket.latest.open();
    MockWebSocket.latest.send(frame(3, 3));
    MockWebSocket.latest.refuse();
    for (let i = 0; i < 4; i += 1) {
      vi.advanceTimersByTime(30_000);
      MockWebSocket.latest.refuse();
    }
    expect(handOver).not.toHaveBeenCalled();
    ws.disconnect();
  });

  it('and the run carries on over SSE from where it stopped', async () => {
    const { ws, sse } = await freshModules();
    ws.connect(RUN, 2, { onUnavailable: (seq) => sse.connectSSE(RUN, seq) });
    MockWebSocket.latest.refuse();
    vi.advanceTimersByTime(1000);
    MockWebSocket.latest.refuse();
    expect(MockEventSource.latest.url).toBe(`/sse/live/${RUN}?last_seq=2`);
    MockEventSource.latest.open();
    for (const m of RUN_MESSAGES) MockEventSource.latest.send(m);
    const s = storeModule.store.get();
    expect(s.frames.map((f) => f.seq)).toEqual([3, 4, 5]);
    expect(s.milestones).toHaveLength(3);
    expect(s.live).toBe(false);
  });
});
