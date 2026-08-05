import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CompareView } from '../visualizations/CompareView.js';

// `/api/compare` has returned a `narrative` since 0.5.43 — the plain-English
// answer to "why did this run win" that the whole comparison feature exists to
// produce. The view fetched it and dropped it on the floor, so the feature was
// invisible in the only place a user would look for it. Task #46 was marked
// done; the API half was.
//
// Found by opening the compare view in a real browser and reading the page,
// not by any test: everything rendered, so everything looked fine.

const NARRATIVE =
  'lower-lr finished ahead of baseline: 0.9020 against 0.7610 (val_accuracy). ' +
  'baseline peaked at 0.8450 on epoch 7 and ended worse, at 0.7610.';

function payload(narrative) {
  const mk = (id, name) => ({
    run: { id, name, final_grade: 'A', primary_metric: 'val_accuracy' },
    frames: [],
    metrics: [
      { canonical_key: 'val_accuracy', epoch: 1, value: 0.6 },
      { canonical_key: 'val_accuracy', epoch: 2, value: 0.7 },
    ],
  });
  return { runs: [mk('r1', 'lower-lr'), mk('r2', 'baseline')], total: 2, narrative };
}

function mountView() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  return { el, view: new CompareView(el) };
}

beforeEach(() => {
  document.body.innerHTML = '';
  // jsdom implements neither of these; the view only needs them not to throw.
  // We are asserting what it RENDERS, not how it measures itself.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // jsdom has no canvas 2d context; the view only needs it not to throw.
  HTMLCanvasElement.prototype.getContext = () => ({
    clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    fillText() {}, fillRect() {}, arc() {}, fill() {}, closePath() {},
    save() {}, restore() {}, setLineDash() {}, setTransform() {}, scale() {},
    translate() {}, rect() {}, clip() {}, createLinearGradient: () => ({ addColorStop() {} }),
    measureText: () => ({ width: 10 }),
  });
});

describe('CompareView narrative', () => {
  it('renders the explanation the API returns', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload(NARRATIVE) })));

    const { el, view } = mountView();
    await view.load(['r1', 'r2']);

    const node = el.querySelector('.cmp-narrative');
    expect(node, 'no .cmp-narrative element — the explanation was dropped').toBeTruthy();
    expect(node.textContent).toContain('peaked at 0.8450 on epoch 7');
  });

  it('says nothing when the runs cannot honestly be compared', async () => {
    // An empty narrative means the engine refused — different metrics, or a gap
    // inside the runs' own noise. Rendering an empty box would imply it had
    // something to say.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload('') })));

    const { el, view } = mountView();
    await view.load(['r1', 'r2']);

    expect(el.querySelector('.cmp-narrative')).toBeNull();
  });

  it('escapes the narrative rather than injecting it as markup', async () => {
    // It is built from run names, which come from log files.
    const evil = 'a<img src=x onerror=alert(1)> beat b';
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload(evil) })));

    const { el, view } = mountView();
    await view.load(['r1', 'r2']);

    expect(el.querySelectorAll('img')).toHaveLength(0);
    expect(el.querySelector('.cmp-narrative').textContent).toContain('<img src=x');
  });
});
