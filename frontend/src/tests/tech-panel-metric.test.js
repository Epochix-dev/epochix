/**
 * The Engineer panel's second chart is titled by the metric it draws — the
 * story's metric, as the frames name it — never "Accuracy" by default.
 *
 * It read "Accuracy" for every run, and labelled whatever it drew "primary
 * metric": a real CatBoost run's unnamed score (an AUC, story metric
 * `val_score`) and its flat eval metric (`val_metric`) were both charted as
 * accuracy. Its stats table also kept its own lower-is-better list, which
 * lacked EER, MSE and FID: their "best" was the worst reading. And a run with
 * no loss still showed "best val ★" in the empty loss chart's legend.
 */
import fs from 'node:fs';
import path from 'node:path';
import { Chart } from 'chart.js';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { TechPanel } from '../panels/TechPanel.js';

const REPO = path.resolve(__dirname, '../../..');

/** A real CatBoost log's eval rows: `N:<TAB>test: X<TAB>best: …`. */
function catboostScores(name) {
  const text = fs.readFileSync(path.join(REPO, 'tests/fixtures/logs', name), 'utf8');
  const rows = [...text.matchAll(/^(\d{1,4}):\ttest: ([\d.]{1,12})\t/gm)];
  return rows.map((m) => ({ epoch: Number(m[1]), value: Number(m[2]) }));
}

function stateOf(points, metric, extraMetrics = []) {
  return {
    run: { primary_metric: 'val_loss' },   // a live run's creation-time placeholder
    frames: points.map((p, i) => ({
      seq: i, epoch: p.epoch, primary_metric: metric, primary_metric_value: p.value,
      grade: 'C-', phase: 'understanding',
    })),
    metrics: [
      ...points.map((p) => ({ canonical_key: metric, epoch: p.epoch, value: p.value })),
      ...extraMetrics,
    ],
  };
}

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

async function mount(state) {
  const panel = new TechPanel({ get: () => state, subscribe: () => () => {} });
  await panel.mount();
  return panel;
}

function metricChart() {
  return Chart.getChart(document.getElementById('accuracy-chart'));
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

describe("the Engineer panel's metric chart", () => {
  it('reads the real CatBoost runs', () => {
    expect(catboostScores('catboost_real_classifier.log')).toHaveLength(60);
    expect(catboostScores('catboost_real_flat_auc.log')).toHaveLength(30);
  });

  it("titles CatBoost's unnamed score by its name, not Accuracy", async () => {
    await mount(stateOf(catboostScores('catboost_real_classifier.log'), 'val_score'));
    const chart = metricChart();
    expect(chart.options.plugins.title.text).not.toMatch(/accuracy/i);
    expect(chart.options.plugins.title.text).toBe('Val score');
    const labels = chart.data.datasets.map((d) => d.label);
    expect(labels).toEqual(['val score', 'best val score ★']);
    // The series drawn is the run's own: 0.9790 → 0.9925.
    expect(chart.data.datasets[0].data[0]).toBeCloseTo(0.9790356, 6);
  });

  it('names no series the run did not report', async () => {
    await mount(stateOf(catboostScores('catboost_real_classifier.log'), 'val_score'));
    // No loss in a CatBoost AUC log: no "best val ★", no "val − train loss".
    for (const id of ['loss-chart', 'gap-chart']) {
      expect(Chart.getChart(document.getElementById(id)).data.datasets).toEqual([]);
    }
  });

  it("titles CatBoost's flat eval metric by its name, not Accuracy", async () => {
    await mount(stateOf(catboostScores('catboost_real_flat_auc.log'), 'val_metric'));
    const chart = metricChart();
    expect(chart.options.plugins.title.text).toBe('Val metric');
    expect(chart.data.datasets.map((d) => d.label).join(' ')).not.toMatch(/accuracy|primary/i);
  });

  it('keeps Accuracy for a run told on validation accuracy', async () => {
    const points = [0.61, 0.7, 0.78].map((value, epoch) => ({ epoch, value }));
    const train = [0.65, 0.76, 0.85].map((value, epoch) => ({ canonical_key: 'accuracy', epoch, value }));
    await mount(stateOf(points, 'val_accuracy', train));
    const chart = metricChart();
    expect(chart.options.plugins.title.text).toBe('Accuracy');
    expect(chart.data.datasets.map((d) => d.label)).toEqual(['train acc', 'val acc', 'best val acc ★']);
  });

  it('draws the accuracy it was given beside a story told on val loss', async () => {
    const points = [0.9, 0.6, 0.5].map((value, epoch) => ({ epoch, value }));
    const acc = [0.6, 0.7, 0.8].map((value, epoch) => ({ canonical_key: 'val_accuracy', epoch, value }));
    await mount(stateOf(points, 'val_loss', acc));
    expect(metricChart().options.plugins.title.text).toBe('Accuracy');
  });

  it('marks the lowest reading best for a lower-is-better story metric', async () => {
    const points = [7.1, 5.2, 5.9].map((value, epoch) => ({ epoch, value }));
    await mount(stateOf(points, 'MAE'));
    const chart = metricChart();
    expect(chart.options.plugins.title.text).toBe('MAE');
    const star = chart.data.datasets.find((d) => d.label === 'best MAE ★');
    expect(star.data.findIndex((v) => v != null)).toBe(1);
  });
});

describe("the Engineer panel's stats table", () => {
  it('takes lower-is-better from the shared list: the best EER is the lowest', async () => {
    const points = [0.3, 0.2, 0.25].map((value, epoch) => ({ epoch, value }));
    await mount(stateOf(points, 'EER'));
    const row = [...document.querySelectorAll('#tech-stats tbody tr')]
      .find((tr) => tr.querySelector('.ts-key').textContent === 'EER');
    expect(row.querySelector('.ts-best').textContent).toBe('0.2000');
    expect(row.querySelector('.ts-ep').textContent).toBe('ep 1');
  });
});
