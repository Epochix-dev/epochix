/**
 * Parameter shares are rounded without claiming a real layer is 0% (or the
 * rest of the model 100%). The bundled Keras demo showed exactly that: two
 * layers of 896 and 650 parameters at "0%" beside a dense layer at "100%".
 */
import { describe, it, expect } from 'vitest';

import { sharePct } from '../visualizations/Distributions.js';

describe('sharePct', () => {
  it('never rounds a real layer down to 0%', () => {
    expect(sharePct((896 / 462400) * 100)).toBe('<1%');
    expect(sharePct((650 / 462400) * 100)).toBe('<1%');
  });

  it('never rounds a partial share up to 100%', () => {
    expect(sharePct((460900 / 462400) * 100)).toBe('>99%');
  });

  it('rounds everything else, and keeps true 0% and 100%', () => {
    expect(sharePct(42.4)).toBe('42%');
    expect(sharePct(100)).toBe('100%');
    expect(sharePct(0)).toBe('0%');
  });
});
