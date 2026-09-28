/**
 * The dashboard shows every setting a parameter search tried.
 *
 * The reports listed them since 0.7.16; the dashboard they were exported from
 * showed only the chosen setting's curve. The panel reads store.crossValidation
 * — from run.config on load, from the live `complete` message, or from the
 * VS Code extension's engine — and hides its section when there is none.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import { setActiveI18n } from '../i18n/apply.js';
import fr from '../i18n/fr.json';
import { createStore } from '../store.js';
import { ParameterSearch } from '../visualizations/ParameterSearch.js';
import { mapFrame } from '../vscode-bridge.js';

const GRID = {
  folds: { score: [0.92, 0.95, 0.91, 0.94, 0.98, 0.96] },
  candidates: {
    'max_depth=3': { score: [0.92, 0.95, 0.91] },
    'max_depth=8': { score: [0.94, 0.98, 0.96] },
  },
};
const PLAIN = { folds: { accuracy: [0.9375, 0.8938, 0.9187, 0.9062, 0.8688] }, candidates: {} };

function mount(initial) {
  document.body.innerHTML =
    '<section id="sec-cv" hidden><div id="parameter-search"></div></section>';
  const store = createStore({ crossValidation: initial });
  new ParameterSearch(
    document.getElementById('parameter-search'),
    document.getElementById('sec-cv'),
  ).mount(store);
  return { store, section: document.getElementById('sec-cv') };
}

describe('the Parameter search panel', () => {
  afterEach(() => setActiveI18n(null));

  it('stays hidden for a run without folds', () => {
    const { section } = mount(null);
    expect(section.hidden).toBe(true);
    expect(section.querySelector('table')).toBeNull();
  });

  it('lists every setting, best first, and marks the one charted', () => {
    const { section } = mount(GRID);
    expect(section.hidden).toBe(false);
    const rows = [...section.querySelectorAll('tbody tr')];
    expect(rows.map((r) => r.querySelector('code').textContent)).toEqual(['max_depth=8', 'max_depth=3']);
    expect(rows[0].classList.contains('is-chosen')).toBe(true);
    expect(rows[1].classList.contains('is-chosen')).toBe(false);
    expect(section.querySelectorAll('.cv-chosen')).toHaveLength(1);
    expect(section.textContent).toContain('Parameter search');
  });

  it('reports a plain cross-validation without a setting column', () => {
    const { section } = mount(PLAIN);
    expect(section.textContent).toContain('Cross-validation');
    expect(section.querySelectorAll('th')).toHaveLength(5);
    expect(section.textContent).toContain('0.905');
  });

  it('appears when the folds arrive later (a live run completing)', () => {
    const { store, section } = mount(null);
    store.set({ crossValidation: GRID });
    expect(section.hidden).toBe(false);
    expect(section.querySelectorAll('tbody tr')).toHaveLength(2);
  });

  it('is in the dashboard language', () => {
    setActiveI18n(fr);
    const { section } = mount(GRID);
    expect(section.textContent).toContain(fr.cv.title_search);
    expect(section.textContent).toContain(fr.cv.chosen);
    expect(section.textContent).not.toContain('Parameter search');
  });

  it('escapes a setting rather than injecting it', () => {
    const { section } = mount({
      folds: { score: [0.5, 0.6] },
      candidates: { '<img src=x onerror=alert(1)>': { score: [0.5] }, b: { score: [0.6] } },
    });
    expect(section.querySelectorAll('img')).toHaveLength(0);
  });
});

describe('where the folds come from', () => {
  beforeEach(() => vi.resetModules());

  it('a live run learns of them from the complete message', async () => {
    // Driven through a real socket message: the handler is not exported.
    const sockets = [];
    vi.stubGlobal('WebSocket', class {
      static OPEN = 1;
      constructor() { this.readyState = 1; sockets.push(this); }
      send() {}
      close() {}
    });
    const { store } = await import('../store.js');
    const { connect, disconnect } = await import('../ws-client.js');
    connect('run-1');
    expect(sockets).toHaveLength(1);
    sockets[0].onmessage({
      data: JSON.stringify({
        v: 1, type: 'complete', run_id: 'run-1', seq: 9,
        payload: { final_grade: 'A', cross_validation: GRID },
      }),
    });
    expect(store.get().crossValidation).toEqual(GRID);
    disconnect();
    vi.unstubAllGlobals();
  });

  it('the VS Code bridge passes on the engine\'s folds', async () => {
    const sent = [];
    window.__EPOCHIX_VSCODE__ = { postMessage: (m) => sent.push(m) };
    const { store } = await import('../store.js');
    const { startVscodeBridge } = await import('../vscode-bridge.js');
    startVscodeBridge(() => {});
    window.dispatchEvent(new MessageEvent('message', {
      data: { type: 'init', theme: 'dark', hasSidecar: false, snapshot: [], crossValidation: GRID },
    }));
    expect(store.get().crossValidation).toEqual(GRID);
    window.dispatchEvent(new MessageEvent('message', {
      data: { type: 'complete', run: { id: 'r', crossValidation: null } },
    }));
    // A summary without folds does not wipe the ones init delivered.
    expect(store.get().crossValidation).toEqual(GRID);
    delete window.__EPOCHIX_VSCODE__;
    expect(mapFrame).toBeTypeOf('function');
  });
});
