/**
 * Every report must arrive labelled.
 *
 * GitHub silently DROPS unknown labels from an `/issues/new?labels=` link. The
 * dashboard asked for `correctness` alone, which did not exist in the repo — so
 * every dashboard report arrived with no label at all, and nothing anywhere
 * reported an error. The extension's own command asked for `bug` and labelled
 * fine, so only one of the two paths worked.
 *
 * Issue #35 came in unlabelled for exactly this reason.
 */
import { describe, it, expect } from 'vitest';

import { REPORT_LABELS } from '../report.js';

// Labels GitHub creates with every new repository, and so cannot go missing.
const GITHUB_DEFAULT_LABELS = new Set([
  'bug',
  'documentation',
  'duplicate',
  'enhancement',
  'good first issue',
  'help wanted',
  'invalid',
  'question',
  'wontfix',
]);

describe('report labels', () => {
  it('includes at least one label GitHub always provides', () => {
    const labels = REPORT_LABELS.split(',').map((l) => l.trim());
    const guaranteed = labels.filter((l) => GITHUB_DEFAULT_LABELS.has(l));
    expect(guaranteed.length).toBeGreaterThan(0);
  });

  it('still asks for the specific category', () => {
    expect(REPORT_LABELS.split(',').map((l) => l.trim())).toContain('correctness');
  });

  it('is a bare comma-separated list, as the issue URL expects', () => {
    expect(REPORT_LABELS).not.toMatch(/\s/);
    expect(REPORT_LABELS.split(',').every((l) => l.length > 0)).toBe(true);
  });
});
