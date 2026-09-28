/**
 * The dashboard ranks a parameter search exactly as the reports do.
 *
 * tests/fixtures/cv_ranking.json is generated from the Python ranking
 * (src/epochix/cross_validation.py) and pinned to it by
 * tests/unit/test_cv_ranking_fixture.py. Every case in it must come out of the
 * JavaScript port identically — same rows, same order, same winner.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { isSearch, summarise } from '../crossValidation.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(
  fs.readFileSync(path.resolve(here, '../../../tests/fixtures/cv_ranking.json'), 'utf-8'),
);

describe('cross-validation ranking parity', () => {
  it('has cases to check', () => {
    expect(Object.keys(CASES).length).toBeGreaterThanOrEqual(7);
  });

  for (const [name, c] of Object.entries(CASES)) {
    it(name, () => {
      expect(isSearch(c.cv)).toBe(c.is_search);
      const got = summarise(c.cv);
      expect(got.map((r) => [r.metric, r.setting, r.folds, r.chosen]))
        .toEqual(c.rows.map((r) => [r.metric, r.setting, r.folds, r.chosen]));
      got.forEach((r, i) => {
        const want = c.rows[i];
        for (const k of ['mean', 'lowest', 'highest']) expect(r[k]).toBeCloseTo(want[k], 12);
        if (want.std === null) expect(r.std).toBeNull();
        else expect(r.std).toBeCloseTo(want.std, 12);
      });
    });
  }
});
