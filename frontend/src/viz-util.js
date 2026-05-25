/**
 * viz-util.js — small shared helpers for the chart visualizations
 * (multi-run comparison, learning curve, engineer panel).
 */

/** Distinct, theme-aligned series colours (cycled for many runs). */
export const SERIES_COLORS = [
  '#7c6dff', '#22d3ee', '#f472b6', '#fbbf24', '#34d399', '#fb923c',
  '#60a5fa', '#a78bfa', '#f87171', '#2dd4bf', '#e879f9', '#facc15',
];

export function seriesColor(i) {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}

/**
 * TensorBoard-style debiased exponential moving average.
 * @param {number[]} values
 * @param {number} weight  0 (none) .. ~0.99 (heavy)
 * @returns {number[]}
 */
export function emaSmooth(values, weight) {
  if (!weight || weight <= 0) return values.slice();
  const out = [];
  let last = 0;
  let debias = 0;
  for (const v of values) {
    if (!Number.isFinite(v)) { out.push(v); continue; }
    last = last * weight + (1 - weight) * v;
    debias = debias * weight + (1 - weight);
    out.push(debias > 0 ? last / debias : v);
  }
  return out;
}

/**
 * Build a sorted {x,y} series for a canonical metric key from metric events.
 * @param {object[]} metrics
 * @param {string} key
 * @param {'epoch'|'step'} [xField]
 * @returns {{x:number,y:number}[]}
 */
export function seriesFromMetrics(metrics, key, xField = 'epoch') {
  if (!metrics?.length) return [];
  return metrics
    .filter((m) => m.canonical_key === key && Number.isFinite(m.value))
    .map((m) => ({ x: m[xField] ?? m.epoch ?? 0, y: m.value }))
    .sort((a, b) => a.x - b.x);
}

/** All canonical metric keys present across a set of metric arrays. */
export function allMetricKeys(metricArrays) {
  const keys = new Set();
  for (const arr of metricArrays) {
    for (const m of arr ?? []) keys.add(m.canonical_key);
  }
  return [...keys].sort();
}

/** Human label for a canonical key. */
export function metricLabel(key) {
  return ({
    train_loss: 'train loss', val_loss: 'val loss',
    val_accuracy: 'val accuracy', accuracy: 'accuracy',
    mAP: 'mAP', mAP50: 'mAP50', MAE: 'MAE', RMSE: 'RMSE',
    EER: 'EER', perplexity: 'perplexity', lr: 'learning rate',
  })[key] ?? key.replace(/_/g, ' ');
}

/** Lower-is-better metrics (affects "best" markers / axis hints). */
export const LOWER_IS_BETTER = new Set([
  'train_loss', 'val_loss', 'loss', 'MAE', 'RMSE', 'MSE',
  'EER', 'perplexity', 'eta', 'epoch_time', 'fid',
]);
