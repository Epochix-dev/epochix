/**
 * Tests for primary-metric formatting in viz-util.js.
 *
 * Regression guard for the "700% accuracy" bug: a raw error metric (MAE≈7)
 * was rendered as a percentage. The primary metric must be formatted by its
 * actual type — accuracy-style as a %, error/loss metrics as raw values.
 */
import { describe, it, expect } from 'vitest';
import { formatPrimaryMetric, isPercentMetric, metricDisplayLabel } from '../viz-util.js';

describe('isPercentMetric', () => {
  it('accuracy-style metrics are percentages', () => {
    for (const k of ['accuracy', 'val_accuracy', 'mAP', 'mAP50', 'F1', 'AUC']) {
      expect(isPercentMetric(k)).toBe(true);
    }
  });
  it('error/loss metrics are NOT percentages', () => {
    for (const k of ['MAE', 'RMSE', 'MSE', 'val_loss', 'train_loss', 'perplexity', 'EER']) {
      expect(isPercentMetric(k)).toBe(false);
    }
  });
});

describe('formatPrimaryMetric', () => {
  it('accuracy renders as a percentage', () => {
    expect(formatPrimaryMetric('val_accuracy', 0.42)).toEqual({
      label: 'Val accuracy', text: '42.0%', pct: true,
    });
  });

  it('mAP50 renders as a percentage', () => {
    expect(formatPrimaryMetric('mAP50', 0.31)).toEqual({
      label: 'mAP50', text: '31.0%', pct: true,
    });
  });

  it('MAE renders as a RAW value — never a percentage (the 700% bug)', () => {
    const out = formatPrimaryMetric('MAE', 5.884);
    expect(out.pct).toBe(false);
    expect(out.label).toBe('MAE');
    expect(out.text).toBe('5.88');           // NOT "588.4%"
    expect(out.text).not.toContain('%');
  });

  it('a large error value stays raw (would have been 700%)', () => {
    expect(formatPrimaryMetric('MAE', 7.0).text).toBe('7.00');
  });

  it('small values keep more precision', () => {
    expect(formatPrimaryMetric('val_loss', 0.0123).text).toBe('0.0123');
  });

  it('large values shed precision', () => {
    expect(formatPrimaryMetric('perplexity', 245.6).text).toBe('245.6');
  });

  it('null / non-finite → em dash', () => {
    expect(formatPrimaryMetric('MAE', null).text).toBe('—');
    expect(formatPrimaryMetric('MAE', NaN).text).toBe('—');
  });
});

describe('metricDisplayLabel', () => {
  it('capitalises plain lowercase labels', () => {
    expect(metricDisplayLabel('accuracy')).toBe('Accuracy');
    expect(metricDisplayLabel('val_accuracy')).toBe('Val accuracy');
  });
  it('preserves deliberate casing', () => {
    expect(metricDisplayLabel('mAP50')).toBe('mAP50');
    expect(metricDisplayLabel('MAE')).toBe('MAE');
    expect(metricDisplayLabel('EER')).toBe('EER');
  });
});
