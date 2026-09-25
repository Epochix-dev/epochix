/**
 * A frame from the extension's engine keeps the name of the series it is from.
 *
 * The bridge dropped it, so the dashboard fell back to the run's metric: once
 * a story moved from one series to another (YOLO's box_loss until the first
 * validation row, then mAP50) both were drawn and formatted as one.
 */
import { describe, it, expect } from 'vitest';
import { mapFrame } from '../vscode-bridge.js';

describe('mapFrame', () => {
  it('carries the frame\'s own metric', () => {
    const frame = mapFrame({
      seq: 3, epoch: 5, progress: 0.05, phase: 'awakening', grade: 'F',
      primaryMetricValue: 0.049, primaryMetric: 'mAP50', confidence: 0.4,
      narrative: 'x', taskType: 'detection',
    });
    expect(frame.primary_metric).toBe('mAP50');
    expect(frame.primary_metric_value).toBe(0.049);
  });
});
