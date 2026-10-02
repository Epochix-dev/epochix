/**
 * The grade card says how this run's letter was reached — the one way that
 * applied, not both.
 *
 * The sentence under the grade first claimed fixed thresholds for every run,
 * which was false of each one graded on improvement; then it named both ways,
 * because a frame did not record which applied. Frames now carry
 * `grade_basis`, and the card says the sentence that is true of the frame in
 * view. A frame without one keeps the sentence that names both.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { setActiveI18n } from '../i18n/apply.js';
import en from '../i18n/en.json';
import fa from '../i18n/fa.json';
import fr from '../i18n/fr.json';
import { JourneyPanel, gradeCaveatText } from '../panels/JourneyPanel.js';
import { mapFrame } from '../vscode-bridge.js';

const BASES = ['thresholds', 'improvement'];

describe('gradeCaveatText', () => {
  afterEach(() => setActiveI18n(null));

  it('has a sentence for each basis in every locale', () => {
    for (const cat of [en, fa, fr]) {
      setActiveI18n(cat);
      for (const basis of BASES) {
        expect(cat.ui.gradeCaveats[basis]).toBeTruthy();
        expect(gradeCaveatText(basis)).toBe(cat.ui.gradeCaveats[basis]);
      }
      expect(cat.ui.gradeCaveats.thresholds).not.toBe(cat.ui.gradeCaveats.improvement);
    }
  });

  it('falls back to the sentence naming both when the frame does not say', () => {
    setActiveI18n(en);
    for (const basis of [null, undefined, '', 'something-new']) {
      expect(gradeCaveatText(basis)).toBe(en.ui.gradeCaveat);
    }
  });

  it('each sentence claims only its own way', () => {
    expect(en.ui.gradeCaveats.thresholds).toMatch(/fixed thresholds/);
    expect(en.ui.gradeCaveats.thresholds).not.toMatch(/improved/);
    expect(en.ui.gradeCaveats.improvement).toMatch(/improved since its first reading/);
    expect(en.ui.gradeCaveats.improvement).not.toMatch(/fixed thresholds/);
  });

  it('the built-in English matches the dictionary, for a page with no dictionary yet', () => {
    setActiveI18n(null);
    for (const basis of BASES) expect(gradeCaveatText(basis)).toBe(en.ui.gradeCaveats[basis]);
    expect(gradeCaveatText(null)).toBe(en.ui.gradeCaveat);
  });
});

describe('the grade card', () => {
  beforeEach(() => {
    setActiveI18n(en);
    document.body.innerHTML =
      '<div id="narrative-text"></div><p class="grade-note" id="grade-note" hidden></p>' +
      '<p class="grade-caveat" id="grade-caveat">placeholder</p>';
  });
  afterEach(() => setActiveI18n(null));

  const render = (frame) => {
    const panel = Object.create(JourneyPanel.prototype);
    panel._i18n = {};
    panel._render({ frames: [frame], currentFrame: frame, run: null, live: false });
    return document.getElementById('grade-caveat').textContent;
  };

  it('says thresholds for a run graded on thresholds', () => {
    const text = render({ narrative: 'x', grade: 'A', grade_basis: 'thresholds' });
    expect(text).toBe(en.ui.gradeCaveats.thresholds);
  });

  it('says improvement for a run graded on improvement', () => {
    const text = render({ narrative: 'x', grade: 'A', grade_basis: 'improvement' });
    expect(text).toBe(en.ui.gradeCaveats.improvement);
  });

  it('follows the frame in view when the story metric changes mid-run', () => {
    // A YOLO run is told on a loss until its first validation row.
    expect(render({ narrative: 'x', grade: 'B', grade_basis: 'improvement' }))
      .toBe(en.ui.gradeCaveats.improvement);
    expect(render({ narrative: 'y', grade: 'A', grade_basis: 'thresholds' }))
      .toBe(en.ui.gradeCaveats.thresholds);
  });

  it('names both for a frame that does not say', () => {
    expect(render({ narrative: 'x', grade: 'I', grade_basis: null })).toBe(en.ui.gradeCaveat);
    expect(render({ narrative: 'x', grade: 'A' })).toBe(en.ui.gradeCaveat);
  });
});

describe('the VS Code bridge', () => {
  const base = {
    seq: 1, epoch: 1, progress: 0.1, phase: 'awakening', grade: 'B',
    primaryMetricValue: 0.8, primaryMetric: 'val_accuracy', confidence: 0.1,
    gradeNote: null, narrative: 'x', taskType: 'classification',
  };

  it('carries how the letter was reached', () => {
    expect(mapFrame({ ...base, gradeBasis: 'improvement' }).grade_basis).toBe('improvement');
    expect(mapFrame({ ...base, gradeBasis: null }).grade_basis).toBe(null);
    expect(mapFrame(base).grade_basis).toBe(null);
  });
});
