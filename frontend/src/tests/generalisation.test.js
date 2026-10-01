/**
 * One reading of the train/validation gap, on every panel that talks about it.
 *
 * On a real ResNet-18 run (tests/fixtures/logs/resnet18_cifar10.log: 99.2%
 * training accuracy, 93.9% validation, validation loss at its lowest on the
 * last epoch) the diagnostics card read "Overfitting — it memorises training
 * data more than it learns" under a red ALERT while the plain-English panel
 * beside it read "a small gap, so it learned the real patterns rather than
 * just memorising". Two rules, two verdicts, and neither followed from the
 * numbers.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { readGap } from '../generalisation.js';
import { Educational } from '../visualizations/Educational.js';
import { TrainingDiagnostics } from '../visualizations/TrainingDiagnostics.js';
import { _renderSummary } from '../panels/HeroPanel.js';

const REPO = path.resolve(__dirname, '../../..');
const LOG = path.join(REPO, 'tests/fixtures/logs/resnet18_cifar10.log');
const EPOCH_LINE =
  /^Epoch (\d{1,4})\/\d{1,4} train_loss=([\d.]{1,12}) train_accuracy=([\d.]{1,12}) val_loss=([\d.]{1,12}) val_accuracy=([\d.]{1,12}) /;

/** The run's metric events, as the dashboard receives them. */
function resnetMetrics() {
  const out = [];
  for (const line of fs.readFileSync(LOG, 'utf8').split(/\r?\n/)) {
    const m = EPOCH_LINE.exec(line);
    if (!m) continue;
    const epoch = Number(m[1]);
    const add = (canonical_key, value) => out.push({ canonical_key, epoch, value: Number(value) });
    add('train_loss', m[2]);
    add('accuracy', m[3]);
    add('val_loss', m[4]);
    add('val_accuracy', m[5]);
  }
  return out;
}

/** Metric events from per-epoch rows of [trainAcc, valAcc, trainLoss, valLoss]. */
function metricsFrom(rows, keys = ['accuracy', 'val_accuracy', 'train_loss', 'val_loss']) {
  return rows.flatMap((row, i) =>
    row.map((value, k) => ({ canonical_key: keys[k], epoch: i + 1, value }))
       .filter((m) => m.value != null));
}

function stateFor(metrics) {
  const valAcc = metrics.filter((m) => m.canonical_key === 'val_accuracy');
  const frames = valAcc.map((m, i) => ({
    seq: i, epoch: m.epoch, primary_metric: 'val_accuracy', primary_metric_value: m.value,
    grade: 'A', phase: 'mastering',
  }));
  return { frames, metrics };
}

function fakeStore(state) {
  return { get: () => state, subscribe: () => () => {} };
}

function render(Panel, metrics) {
  const el = document.createElement('div');
  new Panel(el).mount(fakeStore(stateFor(metrics)));
  return el.textContent.replace(/\s+/g, ' ');
}

describe('the real ResNet-18 run', () => {
  const metrics = resnetMetrics();

  it('is read from the fixture, all 30 epochs', () => {
    expect(metrics.filter((m) => m.canonical_key === 'val_accuracy')).toHaveLength(30);
  });

  it('has a moderate gap with validation still at its best', () => {
    const g = readGap(metrics);
    expect(g.kind).toBe('accuracy');
    expect(g.train).toBeCloseTo(0.9916, 4);
    expect(g.val).toBeCloseTo(0.9387, 4);
    expect(g.size).toBe('moderate');
    expect(g.validation).toBe('at_best');
    expect(g.status).toBe('warn');
  });

  it('is told the same way by both panels, and neither calls it memorising', () => {
    const plain = render(Educational, metrics);
    const card = render(TrainingDiagnostics, metrics);
    for (const text of [plain, card]) {
      expect(text).not.toMatch(/memoris/i);
      expect(text).toMatch(/still improving/i);
    }
    expect(plain).toContain('99.2%');
    expect(plain).toContain('93.9%');
    expect(plain).toContain('a gap of 5.3 points');
    expect(card).toContain('+5.3 pts');
    // The old sentences, by name.
    expect(plain).not.toContain('learned the real patterns');
    expect(card).not.toContain('memorises training data more than it learns');
  });

  it('keeps the sentence in one element, so its bold numbers do not become columns', () => {
    // .edu-analogy is a flex row: with the text loose inside it, every <b>
    // was a flex item of its own and the sentence broke into columns.
    const el = document.createElement('div');
    new Educational(el).mount(fakeStore(stateFor(metrics)));
    const row = el.querySelector('.edu-analogy');
    expect(row.children).toHaveLength(2);
    expect([...row.childNodes].every((n) => n.nodeType === 1)).toBe(true);
    expect(row.children[1].querySelectorAll('b').length).toBeGreaterThanOrEqual(3);
  });

  it('says what the student analogy stands for', () => {
    const plain = render(Educational, metrics);
    expect(plain).toContain('(training data)');
    expect(plain).toContain('(validation data)');
    expect(plain).not.toContain('the real test');
  });
});

describe('readGap', () => {
  it('calls it overfitting only when validation has got worse', () => {
    // Validation peaks at epoch 3 and slides while training keeps improving.
    const metrics = metricsFrom([
      [0.70, 0.68, 0.90, 0.95], [0.80, 0.76, 0.60, 0.70], [0.88, 0.80, 0.40, 0.60],
      [0.93, 0.79, 0.25, 0.68], [0.97, 0.78, 0.12, 0.80], [0.99, 0.77, 0.05, 0.95],
    ]);
    const g = readGap(metrics);
    expect(g.size).toBe('wide');
    expect(g.validation).toBe('past_best');
    expect(g.bestEpoch).toBe(3);
    expect(g.status).toBe('bad');
    const plain = render(Educational, metrics);
    const card = render(TrainingDiagnostics, metrics);
    expect(plain).toMatch(/since epoch 3/);
    expect(plain).toMatch(/memorise/);
    expect(card).toMatch(/Overfitting — validation has got worse since epoch 3/);
  });

  it('a small gap is good, and claims nothing about memorising', () => {
    const metrics = metricsFrom([
      [0.60, 0.59, 1.0, 1.02], [0.75, 0.74, 0.7, 0.72], [0.85, 0.84, 0.45, 0.47],
    ]);
    const g = readGap(metrics);
    expect(g.size).toBe('small');
    expect(g.status).toBe('good');
    expect(render(Educational, metrics)).toMatch(/about the same/);
    expect(render(Educational, metrics)).not.toMatch(/memoris/i);
  });

  it('falls back to the loss gap when there is no accuracy pair', () => {
    const metrics = metricsFrom(
      [[1.0, 1.1], [0.6, 0.9], [0.3, 0.8], [0.1, 0.9], [0.05, 1.1]],
      ['train_loss', 'val_loss'],
    );
    const g = readGap(metrics);
    expect(g.kind).toBe('loss');
    expect(g.size).toBe('wide');
    expect(g.validation).toBe('past_best');
    expect(g.bestEpoch).toBe(3);
  });

  it('does not guess a trend from two readings', () => {
    const g = readGap(metricsFrom([[0.70, 0.60, 0.9, 1.0], [0.90, 0.70, 0.5, 0.9]]));
    expect(g.validation).toBe('unknown');
    expect(g.size).toBe('wide');
  });

  it('is null without a paired series', () => {
    expect(readGap([{ canonical_key: 'val_accuracy', epoch: 1, value: 0.5 }])).toBeNull();
    expect(readGap([])).toBeNull();
  });
});

describe('the architecture count names what it counts', () => {
  let el;
  beforeEach(() => { el = document.createElement('div'); });
  const layer = (layer_type, tech_label, params_str = '10') =>
    ({ layer_type, tech_label, params: 10, params_str });

  it('a ResNet-18 drawn as stem, blocks and head is 12 modules, not 12 layers', () => {
    const arch = [
      layer('Conv2d', 'CONV'), layer('BatchNorm2d', 'NORM'),
      ...Array.from({ length: 8 }, () => layer('BasicBlock', 'BLOCK', '')),
      layer('AdaptiveAvgPool2d', 'POOL'), layer('Linear', 'HEAD'),
    ];
    _renderSummary(el, { architecture: arch });
    expect(el.textContent).toContain('12 modules');
    expect(el.textContent).not.toContain('layers');
  });

  it('a list of plain layers is still counted as layers', () => {
    _renderSummary(el, { architecture: [layer('Conv2D', 'CONV'), layer('Dense', 'HEAD')] });
    expect(el.textContent).toContain('2 layers');
  });
});
