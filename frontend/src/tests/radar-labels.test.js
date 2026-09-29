/**
 * Radar axis names are wrapped, never cut. The skill radar printed
 * "Val Accura" and "Generalisa" for val_accuracy and generalisation.
 */
import { describe, it, expect } from 'vitest';

import { radarLabelLines } from '../visualizations/SkillRadar.js';

describe('radarLabelLines', () => {
  it('keeps every character of the name', () => {
    for (const key of ['val_accuracy', 'generalisation', 'accuracy', 'one_minus_eer', 'tar_at_far_0_001']) {
      expect(radarLabelLines(key).join(' ')).toBe(key.replace(/_/g, ' '));
    }
  });

  it('uses at most two lines', () => {
    expect(radarLabelLines('val_accuracy')).toEqual(['val', 'accuracy']);
    expect(radarLabelLines('tar_at_far_0_001').length).toBeLessThanOrEqual(2);
    expect(radarLabelLines('fitting')).toEqual(['fitting']);
  });
});
