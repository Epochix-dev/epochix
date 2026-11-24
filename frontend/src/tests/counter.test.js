/**
 * The dashboard names the counter a run counts by.
 *
 * A run with no epochs has its own counter in every frame's `epoch` field — a
 * boosting round, an iteration, a step. The learning curve of a nanoGPT run
 * ran to 2000 on an axis labelled "epoch", the Engineer charts were titled
 * "Epoch" under CatBoost's rounds, and the plain-English panel said "Over 60
 * epochs" of sixty of them. The engine says what the number counts on each
 * frame (`counter`); these drive the real panels and read what they drew.
 *
 * A frame without one — nothing in its epoch field, or a run stored before
 * the counter was recorded — is worded as an epoch, exactly as before.
 */
import fs from 'node:fs';
import path from 'node:path';
import { Chart } from 'chart.js';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  COUNTERS, counterLabel, counterWord, frameCounter, latestCounter, sharedCounter,
} from '../counter.js';
import { setActiveI18n } from '../i18n/apply.js';
import { TechPanel } from '../panels/TechPanel.js';
import { frameReportButton, reportFrame } from '../report.js';
import { Educational } from '../visualizations/Educational.js';
import { GradeArcChart } from '../visualizations/GradeArcChart.js';
import { mapFrame } from '../vscode-bridge.js';

const REPO = path.resolve(__dirname, '../../..');
const I18N = Object.fromEntries(['en', 'fr', 'fa'].map((locale) => [
  locale,
  JSON.parse(fs.readFileSync(path.join(__dirname, `../i18n/${locale}.json`), 'utf8')),
]));

/** A real nanoGPT run's evaluation rows: `step N: train loss X, val loss Y`. */
function nanogptSteps() {
  const text = fs.readFileSync(path.join(REPO, 'tests/fixtures/logs/nanogpt_real.log'), 'utf8');
  const rows = [...text.matchAll(/^step (\d{1,6}): train loss [\d.]{1,12}, val loss ([\d.]{1,12})/gm)];
  return rows.map((m) => ({ epoch: Number(m[1]), value: Number(m[2]) }));
}

/** A real CatBoost run's eval rows: `N:<TAB>test: X<TAB>best: …`. */
function catboostRounds() {
  const text = fs.readFileSync(path.join(REPO, 'tests/fixtures/logs/catboost_real_classifier.log'), 'utf8');
  const rows = [...text.matchAll(/^(\d{1,4}):\ttest: ([\d.]{1,12})\t/gm)];
  return rows.map((m) => ({ epoch: Number(m[1]), value: Number(m[2]) }));
}

function framesOf(points, metric, counter) {
  return points.map((p, i) => ({
    seq: i, epoch: p.epoch, primary_metric: metric, primary_metric_value: p.value,
    grade: 'C-', phase: 'understanding', ...(counter === undefined ? {} : { counter }),
  }));
}

const EPOCHS = [0.61, 0.7, 0.78, 0.82].map((value, i) => ({ epoch: i + 1, value }));

afterEach(() => setActiveI18n(null));

describe('what a run counts by', () => {
  it('reads the recordings', () => {
    const steps = nanogptSteps();
    expect(steps).toHaveLength(9);
    expect(steps.at(-1)).toEqual({ epoch: 2000, value: 1.8857 });
    expect(catboostRounds()).toHaveLength(60);
  });

  it('is read from the frames: the latest one that says', () => {
    expect(COUNTERS).toEqual(['epoch', 'step', 'iteration', 'round']);
    expect(latestCounter([{ counter: 'step' }, { counter: 'iteration' }, { counter: null }]))
      .toBe('iteration');
    expect(frameCounter({ counter: 'round' })).toBe('round');
  });

  it('is an epoch where no frame says — as every run was worded before', () => {
    expect(latestCounter([])).toBe('epoch');
    expect(latestCounter(undefined)).toBe('epoch');
    expect(latestCounter([{ epoch: 3 }, { counter: null }])).toBe('epoch');
    expect(frameCounter({ counter: 'fortnight' })).toBe('epoch');
    expect(counterWord(null, 'many')).toBe('epochs');
    expect(counterWord(undefined, 'short')).toBe('ep');
  });

  it('counts readings, not steps, where the number is a count of readings', () => {
    // Nine readings 250 steps apart are not "9 steps".
    expect(counterWord('step', 'readings')).toBe('readings');
    expect(counterWord('round', 'readings')).toBe('readings');
    expect(counterWord('epoch', 'readings')).toBe('epochs');
    expect(counterWord('step', 'many')).toBe('steps');
  });

  it('has a label in every language for every kind', () => {
    const words = {};
    for (const [locale, dict] of Object.entries(I18N)) {
      setActiveI18n(dict);
      words[locale] = COUNTERS.map((kind) => counterLabel(kind));
      expect(new Set(words[locale]).size).toBe(COUNTERS.length);
    }
    expect(words.en).toEqual(['Epoch', 'Step', 'Iteration', 'Round']);
    expect(words.fr).toEqual(['Époque', 'Étape', 'Itération', 'Tour']);
    expect(words.fa[0]).toBe(I18N.fa.labels.epoch);
    // No dictionary loaded: English, not a key.
    setActiveI18n(null);
    expect(counterLabel('round')).toBe('Round');
    expect(counterLabel(null)).toBe('Epoch');
  });

  it('is shared by runs only when they all count the same way', () => {
    const steps = framesOf(nanogptSteps(), 'val_loss', 'step');
    expect(sharedCounter([steps, steps])).toBe('step');
    expect(sharedCounter([steps, framesOf(EPOCHS, 'val_loss', 'epoch')])).toBeNull();
    expect(sharedCounter([framesOf(EPOCHS, 'val_loss'), framesOf(EPOCHS, 'val_loss')])).toBe('epoch');
  });

  it("reaches the dashboard from the extension's engine", () => {
    const host = { seq: 1, epoch: 250, counter: 'step', primaryMetric: 'val_loss', primaryMetricValue: 2.4 };
    expect(mapFrame(host).counter).toBe('step');
    expect(mapFrame({ ...host, counter: undefined }).counter).toBeNull();
  });
});

describe("the learning curve's axis", () => {
  let drawn;

  function draw(frames) {
    const wrap = document.createElement('div');
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    document.body.appendChild(wrap);
    const state = { run: { primary_metric: 'val_loss' }, frames, metrics: [] };
    const chart = new GradeArcChart(canvas);
    chart.mount({ get: () => state, subscribe: (fn) => { fn(state); return () => {}; } });
    drawn.length = 0; // mount drew once already
    chart._draw();
    return drawn.map((d) => d.text);
  }

  beforeEach(() => {
    drawn = [];
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    HTMLCanvasElement.prototype.getContext = () => ({
      clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
      fillText(text, x, y) { drawn.push({ text, x, y }); },
      fillRect() {}, arc() {}, fill() {}, closePath() {},
      save() {}, restore() {}, setLineDash() {}, setTransform() {}, scale() {},
      translate() {}, rect() {}, clip() {}, createLinearGradient: () => ({ addColorStop() {} }),
      measureText: () => ({ width: 10 }),
    });
  });

  it('is named "step" under a nanoGPT run, which has no epochs', () => {
    const texts = draw(framesOf(nanogptSteps(), 'val_loss', 'step'));
    expect(texts).toContain('step');
    expect(texts).not.toContain('epoch');
    // The ticks are the run's own steps.
    expect(texts).toContain(2000);
  });

  it('is named "round" under a boosting run', () => {
    const texts = draw(framesOf(catboostRounds(), 'val_score', 'round'));
    expect(texts).toContain('round');
    expect(texts).not.toContain('epoch');
  });

  it('is still "epoch" under a run that counts epochs, or says nothing', () => {
    expect(draw(framesOf(EPOCHS, 'val_accuracy', 'epoch'))).toContain('epoch');
    expect(draw(framesOf(EPOCHS, 'val_accuracy'))).toContain('epoch');
  });
});

describe("the Engineer panel's axis", () => {
  /** A 2D context that accepts every call Chart.js makes and draws nothing. */
  function inertContext(canvas) {
    const handler = {
      get(target, prop) {
        if (prop === 'canvas') return canvas;
        if (prop === 'measureText') return () => ({ width: 10 });
        if (prop in target) return target[prop];
        return () => new Proxy({}, handler);
      },
      set(target, prop, value) { target[prop] = value; return true; },
    };
    return new Proxy({}, handler);
  }

  async function titles(frames, metric) {
    const state = {
      run: { primary_metric: 'val_loss' },
      frames,
      metrics: frames.map((f) => ({ canonical_key: metric, epoch: f.epoch, value: f.primary_metric_value })),
    };
    const panel = new TechPanel({ get: () => state, subscribe: () => () => {} });
    await panel.mount();
    const ids = ['loss-chart', 'accuracy-chart', 'gap-chart', 'lr-chart'];
    const charts = ids.map((id) => Chart.getChart(document.getElementById(id))).filter(Boolean);
    expect(charts.length).toBeGreaterThanOrEqual(3);
    return [...new Set(charts.map((c) => c.options.scales.x.title.text))];
  }

  beforeEach(() => {
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    HTMLCanvasElement.prototype.getContext = function getContext() { return inertContext(this); };
    document.body.innerHTML = `
      <canvas id="loss-chart"></canvas>
      <canvas id="accuracy-chart"></canvas>
      <canvas id="gap-chart"></canvas>
      <div><canvas id="lr-chart"></canvas></div>
      <div id="tech-stats"></div>`;
  });

  afterEach(() => {
    for (const id of ['loss-chart', 'accuracy-chart', 'gap-chart', 'lr-chart']) {
      Chart.getChart(document.getElementById(id))?.destroy();
    }
  });

  it('titles every chart by the steps of a nanoGPT run', async () => {
    expect(await titles(framesOf(nanogptSteps(), 'val_loss', 'step'), 'val_loss')).toEqual(['Step']);
  });

  it('titles every chart by the rounds of a boosting run', async () => {
    expect(await titles(framesOf(catboostRounds(), 'val_score', 'round'), 'val_score')).toEqual(['Round']);
  });

  it('still titles a run with epochs "Epoch"', async () => {
    expect(await titles(framesOf(EPOCHS, 'val_accuracy', 'epoch'), 'val_accuracy')).toEqual(['Epoch']);
    for (const id of ['loss-chart', 'accuracy-chart', 'gap-chart', 'lr-chart']) {
      Chart.getChart(document.getElementById(id))?.destroy();
    }
    expect(await titles(framesOf(EPOCHS, 'val_accuracy'), 'val_accuracy')).toEqual(['Epoch']);
  });
});

describe('the sentences around the charts', () => {
  function plain(frames) {
    const el = document.createElement('div');
    const state = { frames, metrics: [], run: { primary_metric: 'val_loss' } };
    new Educational(el).mount({ get: () => state, subscribe: () => () => {} });
    return el.textContent.replace(/\s+/g, ' ');
  }

  it('count sixty boosting rounds as rounds', () => {
    const text = plain(framesOf(catboostRounds(), 'val_score', 'round'));
    expect(text).toContain('Over 60 rounds');
    expect(text).not.toMatch(/epoch/i);
  });

  it('count a run with epochs in epochs, as before', () => {
    expect(plain(framesOf(EPOCHS, 'val_accuracy', 'epoch'))).toContain('Over 4 epochs');
    expect(plain(framesOf(EPOCHS, 'val_accuracy'))).toContain('Over 4 epochs');
  });

  it('report a disputed reading by what it was counted in', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const frame = { epoch: 2000, counter: 'step', narrative: 'x', primary_metric: 'val_loss' };
    reportFrame(frame, { task_type: 'custom' }, '0.0.0');
    const url = decodeURIComponent(String(open.mock.calls[0][0]).replace(/\+/g, ' '));
    expect(url).toContain('Wrong reading at step 2000');
    expect(url).toMatch(/step {8,9}2000/);
    expect(url).not.toMatch(/epoch\s+2000/);
    expect(frameReportButton(frame)).toContain('the reading at step 2000');
    expect(frameReportButton({ epoch: 3 })).toContain('the reading at epoch 3');
    open.mockRestore();
  });
});
