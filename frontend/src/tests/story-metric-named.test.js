/**
 * The dashboard says what the story's metric is by its name, as the frames
 * give it — never by the shape of its numbers, never by the run record.
 *
 * Driving a real CatBoost run through `epochix --live` found two ways it did
 * not. The "In plain English" panel called any rising value between 0 and 1
 * accuracy — CatBoost's unnamed score (an AUC, 0.979 → 0.992) read "went from
 * 97.9% to 99.2% accuracy" and "gets more than 9 in 10 right on data it hasn't
 * seen". And the learning curve took its metric from the run record, which a
 * live run left at its creation-time `val_loss`: a live Keras run's validation
 * accuracy drew as an inverted "val loss" curve.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, beforeEach } from 'vitest';

import { latestPrimaryKey } from '../viz-util.js';
import { Educational } from '../visualizations/Educational.js';
import { GradeArcChart } from '../visualizations/GradeArcChart.js';

const REPO = path.resolve(__dirname, '../../..');

/** The real CatBoost classifier's eval rows: `N:<TAB>test: X<TAB>best: …`. */
function catboostScores() {
  const text = fs.readFileSync(path.join(REPO, 'tests/fixtures/logs/catboost_real_classifier.log'), 'utf8');
  const rows = [...text.matchAll(/^(\d{1,4}):\ttest: ([\d.]{1,12})\t/gm)];
  return rows.map((m) => ({ epoch: Number(m[1]), value: Number(m[2]) }));
}

function framesOf(points, metric) {
  return points.map((p, i) => ({
    seq: i, epoch: p.epoch, primary_metric: metric, primary_metric_value: p.value,
    grade: 'C-', phase: 'understanding',
  }));
}

function plain(frames, metrics = []) {
  const el = document.createElement('div');
  const state = { frames, metrics, run: { primary_metric: 'val_loss' } };
  new Educational(el).mount({ get: () => state, subscribe: () => () => {} });
  return el.textContent.replace(/\s+/g, ' ');
}

const RISING = [0.61, 0.7, 0.78, 0.82].map((value, i) => ({ epoch: i + 1, value }));

describe('the plain-English panel', () => {
  it('reads the real CatBoost run, all 60 rounds', () => {
    const points = catboostScores();
    expect(points).toHaveLength(60);
    expect(points[0].value).toBe(0.9790356);
  });

  it('does not call CatBoost\'s unnamed score accuracy', () => {
    const text = plain(framesOf(catboostScores(), 'val_score'));
    expect(text).toContain('its val score went from 0.9790 to 0.9925');
    expect(text).not.toMatch(/accuracy|%|right on data/);
    // The name does not say which way is better, so nothing was "learned".
    expect(text).toContain('Changed');
    expect(text).not.toContain('Learned');
  });

  it('counts sixty rounds numbered from 0 as sixty, not 59', () => {
    expect(plain(framesOf(catboostScores(), 'val_score'))).toContain('Over 60 epochs');
  });

  for (const metric of ['val_AUC', 'val_f1', 'mAP50', 'val_r2', 'val_score']) {
    it(`does not tell ${metric} as accuracy, or count it as answers right`, () => {
      const text = plain(framesOf(RISING, metric));
      expect(text).not.toMatch(/accuracy|right on data/);
    });
  }

  it('tells validation accuracy as accuracy, with the unseen-data meter', () => {
    const text = plain(framesOf(RISING, 'val_accuracy'));
    expect(text).toContain('went from 61.0% to 82.0% accuracy');
    expect(text).toContain('right on data it hasn\'t seen');
    expect(text).toContain('Learned');
  });

  it('does not say training accuracy was measured on unseen data', () => {
    const text = plain(framesOf(RISING, 'accuracy'));
    expect(text).toContain('82.0% accuracy');
    expect(text).not.toContain('right on data it hasn\'t seen');
  });

  it('says a falling loss was reduced, by its name', () => {
    const falling = [0.9, 0.6, 0.45].map((value, i) => ({ epoch: i, value }));
    const text = plain(framesOf(falling, 'val_loss'));
    expect(text).toContain('reduced its val loss from 0.9000 to 0.4500');
    expect(text).toContain('Over 3 epochs');
  });

  it('does not call a falling score a reduced error', () => {
    const falling = [0.9, 0.8, 0.7].map((value, i) => ({ epoch: i + 1, value }));
    const text = plain(framesOf(falling, 'val_AUC'));
    expect(text).not.toMatch(/reduced|error|Learned/);
  });

  it('keeps a fractional epoch count as before', () => {
    const halves = [0.5, 1, 1.5, 2].map((epoch, i) => ({ epoch, value: 0.5 + i / 10 }));
    expect(plain(framesOf(halves, 'val_accuracy'))).toContain('Over 2 epochs');
  });
});

describe('the learning curve', () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    HTMLCanvasElement.prototype.getContext = () => ({
      clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
      fillText() {}, fillRect() {}, arc() {}, fill() {}, closePath() {},
      save() {}, restore() {}, setLineDash() {}, setTransform() {}, scale() {},
      translate() {}, rect() {}, clip() {}, createLinearGradient: () => ({ addColorStop() {} }),
      measureText: () => ({ width: 10 }),
    });
  });

  it('takes the metric from the frames, not a run record still saying val_loss', () => {
    const wrap = document.createElement('div');
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    document.body.appendChild(wrap);
    const state = {
      run: { primary_metric: 'val_loss' },
      frames: framesOf(RISING, 'val_accuracy'),
      metrics: [],
    };
    const chart = new GradeArcChart(canvas);
    chart.mount({ get: () => state, subscribe: (fn) => { fn(state); return () => {}; } });
    expect(chart._primaryKey).toBe('val_accuracy');
  });

  it('latestPrimaryKey reads the last frame that names one', () => {
    expect(latestPrimaryKey([{ primary_metric: 'val_loss' }, { primary_metric: 'val_accuracy' }, {}]))
      .toBe('val_accuracy');
    expect(latestPrimaryKey([])).toBeNull();
    expect(latestPrimaryKey(undefined)).toBeNull();
  });
});

describe('the phase journey', () => {
  it('names each phase and its epochs, with no flavour line no log shows', async () => {
    const { PhaseJourney } = await import('../visualizations/PhaseJourney.js');
    const el = document.createElement('div');
    const phases = ['awakening', 'learning', 'understanding', 'mastering', 'polishing'];
    const frames = phases.map((phase, i) => ({
      seq: i, epoch: i, phase, grade: 'B', primary_metric: 'val_accuracy', primary_metric_value: 0.5,
    }));
    const state = { frames, currentFrame: frames[frames.length - 1] };
    new PhaseJourney(el).mount({ get: () => state, subscribe: () => () => {} });
    const text = el.textContent.replace(/\s+/g, ' ');
    expect(text).toContain('Awakening');
    expect(text).toContain('Polishing');
    expect(text).not.toMatch(/signal from noise|patterns forming|memoris|refining the edges|final gains/);
  });
});

describe('the learning curve\'s grade lines', () => {
  const CLASSIFICATION = {
    lower_better: false,
    bands: [
      ['A+', 0.95], ['A', 0.9], ['A-', 0.87], ['B+', 0.82], ['B', 0.75], ['B-', 0.7],
      ['C+', 0.65], ['C', 0.6], ['C-', 0.55], ['D', 0.5], ['F', 0.0],
    ].map(([grade, value]) => ({ grade, value })),
  };

  it('are the bands the run was graded on, without F', async () => {
    const { gradeLines } = await import('../visualizations/GradeArcChart.js');
    const lines = gradeLines({ config: { grade_bands: CLASSIFICATION } });
    expect(lines.map((l) => [l.grade, l.v])).toEqual([
      ['A+', 0.95], ['A', 0.9], ['A-', 0.87], ['B+', 0.82], ['B', 0.75], ['B-', 0.7],
      ['C+', 0.65], ['C', 0.6], ['C-', 0.55], ['D', 0.5],
    ]);
    // The typed copy it replaced put A+ at 0.97 and A at 0.93.
    expect(lines.find((l) => l.grade === 'A+').v).toBe(0.95);
  });

  it('are none for a run not graded on bands, or a lower-is-better one', async () => {
    const { gradeLines } = await import('../visualizations/GradeArcChart.js');
    expect(gradeLines({ config: {} })).toEqual([]);
    expect(gradeLines({})).toEqual([]);
    expect(gradeLines(undefined)).toEqual([]);
    expect(gradeLines({ config: { grade_bands: { ...CLASSIFICATION, lower_better: true } } })).toEqual([]);
  });

  it('never stack two letters on top of each other', async () => {
    const { GradeArcChart } = await import('../visualizations/GradeArcChart.js');
    const drawn = [];
    HTMLCanvasElement.prototype.getContext = () => ({
      clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
      fillText(text, x, y) { drawn.push({ text, x, y }); },
      fillRect() {}, arc() {}, fill() {}, closePath() {},
      save() {}, restore() {}, setLineDash() {}, setTransform() {}, scale() {},
      translate() {}, rect() {}, clip() {}, createLinearGradient: () => ({ addColorStop() {} }),
      measureText: () => ({ width: 10 }),
    });
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    const wrap = document.createElement('div');
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    document.body.appendChild(wrap);
    const state = {
      run: { config: { grade_bands: CLASSIFICATION } },
      frames: framesOf(RISING, 'val_accuracy'),
      metrics: [],
    };
    const chart = new GradeArcChart(canvas);
    chart.mount({ get: () => state, subscribe: (fn) => { fn(state); return () => {}; } });
    drawn.length = 0; // mount drew once already
    chart._draw();
    const letters = drawn.filter((d) => d.x === 2).map((d) => d.y).sort((a, b) => a - b);
    expect(letters.length).toBeGreaterThan(0);
    for (let i = 1; i < letters.length; i++) {
      expect(letters[i] - letters[i - 1]).toBeGreaterThanOrEqual(10);
    }
  });
});
