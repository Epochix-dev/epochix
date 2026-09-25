/**
 * The grade card says when its letter deserves less weight than it looks.
 *
 * An 11-epoch run and a 200-epoch run got equally confident letters. The
 * engines now mark a frame whose letter rests on few readings, or was taken
 * while the metric was still setting new bests (frame.grade_note); the
 * dashboard says so under the grade, in the reader's language.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { setActiveI18n } from '../i18n/apply.js';
import en from '../i18n/en.json';
import fa from '../i18n/fa.json';
import fr from '../i18n/fr.json';
import { JourneyPanel, gradeNoteText } from '../panels/JourneyPanel.js';
import { mapFrame } from '../vscode-bridge.js';

const NOTES = ['few_readings', 'still_improving'];

describe('gradeNoteText', () => {
  afterEach(() => setActiveI18n(null));

  it('has a sentence for every note in every locale', () => {
    for (const cat of [en, fa, fr]) {
      setActiveI18n(cat);
      for (const note of NOTES) {
        expect(cat.ui.gradeNotes[note]).toBeTruthy();
        expect(gradeNoteText(note)).toBe(cat.ui.gradeNotes[note]);
      }
    }
  });

  it('says nothing when there is nothing to qualify', () => {
    expect(gradeNoteText(null)).toBe('');
    expect(gradeNoteText(undefined)).toBe('');
  });
});

describe('the grade card', () => {
  beforeEach(() => {
    document.body.innerHTML =
      '<div id="narrative-text"></div><p class="grade-note" id="grade-note" hidden></p>';
  });

  const render = (frame) => {
    const panel = Object.create(JourneyPanel.prototype);
    panel._i18n = {};
    panel._render({ frames: [frame], currentFrame: frame, run: null, live: false });
    return document.getElementById('grade-note');
  };

  it('shows the note for a provisional letter', () => {
    const el = render({ narrative: 'x', grade: 'A+', grade_note: 'few_readings' });
    expect(el.hidden).toBe(false);
    expect(el.textContent).toMatch(/fewer than five readings/);
  });

  it('hides it again when the letter settles', () => {
    render({ narrative: 'x', grade: 'A', grade_note: 'still_improving' });
    const el = render({ narrative: 'y', grade: 'A', grade_note: null });
    expect(el.hidden).toBe(true);
    expect(el.textContent).toBe('');
  });
});

describe('the VS Code bridge', () => {
  it('carries the engine\'s grade note', () => {
    const frame = mapFrame({
      seq: 1, epoch: 1, progress: 0.1, phase: 'awakening', grade: 'B',
      primaryMetricValue: 0.8, primaryMetric: 'val_accuracy', confidence: 0.1,
      gradeNote: 'few_readings', narrative: 'x', taskType: 'classification',
    });
    expect(frame.grade_note).toBe('few_readings');
  });
});
