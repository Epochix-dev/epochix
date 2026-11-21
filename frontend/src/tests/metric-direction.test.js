/**
 * The dashboard reads which way is better for a metric exactly as the engine.
 *
 * It had a list of its own, eleven names long. Of the 34 metric names the
 * corpus logs report, it read 10 the wrong way up: box_loss, cls_loss and
 * dfl_loss (every YOLO run), log_loss, val_log_loss, error_rate,
 * val_error_rate, eval0_loss, val_MAE and val_MSE. A falling YOLO loss was
 * carded red as worse and its meter emptied as it improved. None of the panels
 * below had a test.
 *
 * The tables are generated from Python (direction.generated.js), and the
 * engine's own answers — the golden the extension replays — are replayed here.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { createStore } from '../store.js';
import { isLowerBetter, metricLowerBetter } from '../viz-util.js';
import { ConfidenceBars } from '../visualizations/ConfidenceBars.js';
import { LearningMeter } from '../visualizations/LearningMeter.js';
import { Distributions } from '../visualizations/Distributions.js';
import { SkillsPanel } from '../panels/SkillsPanel.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const GOLDEN = JSON.parse(fs.readFileSync(
  path.join(REPO, 'epochix-vscode/src/test/fixtures/grading.golden.json'), 'utf8',
)).metric_lower_better;

// The ten names the old list read upside down, from the corpus.
const WERE_UPSIDE_DOWN = [
  'box_loss', 'cls_loss', 'dfl_loss', 'log_loss', 'val_log_loss',
  'error_rate', 'val_error_rate', 'eval0_loss', 'val_MAE', 'val_MSE',
];

describe('metricLowerBetter', () => {
  it('answers as the engine for every name in its golden', () => {
    const names = Object.keys(GOLDEN);
    expect(names.length).toBeGreaterThan(400);
    // Every answer kind is in there, or the comparison proves less than it says.
    expect(new Set(Object.values(GOLDEN))).toEqual(new Set([true, false, null]));
    const wrong = names.filter((n) => (metricLowerBetter(n) ?? null) !== GOLDEN[n]);
    expect(wrong).toEqual([]);
  });

  it('reads the corpus names the old list had backwards as lower-is-better', () => {
    for (const name of WERE_UPSIDE_DOWN) expect(isLowerBetter(name), name).toBe(true);
  });

  it('says nothing for a name that says nothing', () => {
    expect(metricLowerBetter('eta')).toBeUndefined();
    expect(metricLowerBetter('epoch_time')).toBeUndefined();
    expect(metricLowerBetter(null)).toBeUndefined();
    expect(isLowerBetter('eta')).toBe(false);
  });
});

const ev = (key, epoch, value) => ({ canonical_key: key, epoch, value });

function storeWith(state) {
  return createStore({
    run: null, frames: [], currentFrame: null, metrics: [], architecture: null, ...state,
  });
}

describe('the metric cards', () => {
  let el;
  beforeEach(() => { el = document.createElement('div'); });

  function cards(metrics) {
    new ConfidenceBars(el).mount(storeWith({ metrics }));
    return Object.fromEntries([...el.querySelectorAll('.mc')].map((card) => [
      card.querySelector('.mc-name').getAttribute('title'),
      card.querySelector('.mc-delta').className.replace('mc-delta ', ''),
    ]));
  }

  it('call a falling loss better and a rising error worse, whatever its name', () => {
    const got = cards([
      ev('box_loss', 1, 1.2), ev('box_loss', 2, 0.9),
      ev('val_MAE', 1, 2.0), ev('val_MAE', 2, 2.5),
      ev('val_accuracy', 1, 0.6), ev('val_accuracy', 2, 0.7),
    ]);
    expect(got).toEqual({ box_loss: 'good', val_MAE: 'bad', val_accuracy: 'good' });
  });

  it('call a change neither better nor worse where the name does not say', () => {
    expect(cards([ev('eta', 1, 30), ev('eta', 2, 20)])).toEqual({ eta: 'flat' });
  });

  it('show the latest value and nothing invented when there are no metrics', () => {
    new ConfidenceBars(el).mount(storeWith({ metrics: [] }));
    expect(el.innerHTML).toBe('');
    cards([ev('val_loss', 1, 0.5), ev('val_loss', 2, 0.25)]);
    expect(el.querySelector('.mc-value').textContent).toBe('0.2500');
  });
});

describe('the learning meter', () => {
  const frame = (primary_metric, primary_metric_value) => ({ primary_metric, primary_metric_value });

  function fill(frames) {
    const el = document.createElement('div');
    new LearningMeter(el).mount(storeWith({ frames, currentFrame: frames.at(-1) }));
    const rects = el.querySelectorAll('rect');
    const fillRect = [...rects].find((r) => r.getAttribute('clip-path'));
    return { height: Number(fillRect.getAttribute('height')), text: el.querySelector('text').textContent };
  }

  it('fills up as a YOLO loss falls, and empties as an error grows', () => {
    const falling = fill([frame('box_loss', 1.2), frame('box_loss', 0.9), frame('box_loss', 0.6)]);
    const rising = fill([frame('val_MAE', 2.0), frame('val_MAE', 2.5), frame('val_MAE', 3.0)]);
    expect(falling.height).toBeGreaterThan(0);
    expect(rising.height).toBe(0);
    expect(falling.height).toBe(172); // the tube's full height: the best reading so far
  });

  it('shows no reading as empty, not as a value', () => {
    const el = document.createElement('div');
    new LearningMeter(el).mount(storeWith({}));
    expect(el.querySelector('text').textContent).toBe('—');
  });
});

describe('the metric spread', () => {
  it('marks which way is better only where the name says', () => {
    const el = document.createElement('div');
    new Distributions(el).mount(storeWith({ metrics: [
      ev('box_loss', 1, 1.2), ev('box_loss', 2, 0.9), ev('box_loss', 3, 0.7),
      ev('eta', 1, 30), ev('eta', 2, 20), ev('eta', 3, 10),
    ] }));
    const marks = Object.fromEntries([...el.querySelectorAll('.dist-row')]
      .filter((row) => row.querySelector('.dist-box-track'))
      .map((row) => [
        row.querySelector('.dist-row-label').getAttribute('title'),
        row.querySelector('.dist-pct').textContent,
      ]));
    expect(marks).toEqual({ box_loss: '↓', eta: '' });
  });
});

describe('the skills panel', () => {
  it('mounts its radar, meter and cards where the page has room for them', () => {
    document.body.innerHTML = `
      <div id="skill-radar"></div><div id="learning-meter"></div><div id="confidence-bars"></div>`;
    const s = storeWith({ metrics: [ev('val_loss', 1, 0.5), ev('val_loss', 2, 0.4)] });
    const panel = new SkillsPanel(s);
    panel.mount();
    expect(document.querySelector('#learning-meter svg')).not.toBeNull();
    expect(document.querySelector('#confidence-bars .mc')).not.toBeNull();
    panel.unmount();
    document.body.innerHTML = '';
  });
});
