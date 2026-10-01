/**
 * The sentence under the grade says how the grade was reached — both ways.
 *
 * It read "Graded against fixed thresholds for this task type". That is false
 * for every run graded on improvement: any loss-only log, an XGBoost log loss,
 * a LightGBM AUC. A real LightGBM classifier at 98.4% validation AUC was shown
 * a C- under that sentence — the letter measured how little the AUC had moved,
 * and the card said it measured where it stood.
 *
 * Which way a particular run was graded is not on the frame, so the sentence
 * names both rather than the one that is usually true.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import en from '../i18n/en.json';
import fa from '../i18n/fa.json';
import fr from '../i18n/fr.json';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const INDEX = path.resolve(HERE, '..', '..', 'index.html');

// The words each language uses for the two ways a grade is reached.
const BOTH_WAYS = {
  en: [en, 'thresholds', 'improved'],
  fr: [fr, 'seuils', 'progression'],
  fa: [fa, 'آستانه', 'بهبود'],
};

describe('the grade caveat', () => {
  for (const [locale, [dict, thresholds, improvement]] of Object.entries(BOTH_WAYS)) {
    it(`names both ways a grade is reached (${locale})`, () => {
      const text = dict.ui.gradeCaveat;
      expect(text).toContain(thresholds);
      expect(text).toContain(improvement);
    });
  }

  it('does not say every grade is a threshold grade', () => {
    expect(en.ui.gradeCaveat).not.toMatch(/^Graded against fixed thresholds/);
  });

  it('is the same sentence in the page before the dictionary loads', () => {
    const html = fs.readFileSync(INDEX, 'utf8');
    const m = html.match(/data-i18n="ui\.gradeCaveat">([^<]+)</);
    expect(m, 'index.html lost its grade caveat').toBeTruthy();
    expect(m[1].replace(/\s+/g, ' ').trim()).toBe(en.ui.gradeCaveat);
  });
});
