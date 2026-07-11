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

/**
 * Canonical metrics that are 0–1 fractions and read naturally as a percentage
 * (accuracy family). Everything else — MAE, RMSE, loss, perplexity, cm error,
 * … — is a raw value and must NOT be multiplied by 100 or suffixed with "%".
 */
export const PERCENT_METRICS = new Set([
  'accuracy', 'val_accuracy', 'mAP', 'mAP50', 'F1', 'f1',
  'AUC', 'auc', 'top1', 'top5', 'precision', 'recall',
]);

/** True when the primary metric should be displayed as a percentage. */
export function isPercentMetric(key) {
  return PERCENT_METRICS.has(key);
}

/**
 * Display label for a metric, capitalised for a stat chip. Metrics with
 * deliberate casing (mAP50, MAE, RMSE, EER, F1) are left untouched; plain
 * lowercase labels ("accuracy", "val loss") get a leading capital.
 */
export function metricDisplayLabel(key) {
  const raw = metricLabel(key || 'metric');
  return /[A-Z]/.test(raw) ? raw : raw.charAt(0).toUpperCase() + raw.slice(1);
}

/**
 * Format the primary metric for a stat chip / meter: a correct label and value
 * string for ANY task. Accuracy-style metrics render as `NN.N%`; error/loss
 * metrics render as their raw value (adaptive precision) — never as a bogus
 * percentage (which produced e.g. "700%" when MAE≈7 was treated as accuracy).
 *
 * @param {string|null|undefined} key   canonical primary-metric key (run.primary_metric)
 * @param {number|null|undefined} value raw primary_metric_value
 * @returns {{ label: string, text: string, pct: boolean }}
 */
export function formatPrimaryMetric(key, value) {
  const label = metricDisplayLabel(key);
  if (value == null || !Number.isFinite(value)) return { label, text: '—', pct: false };
  if (isPercentMetric(key)) return { label, text: `${(value * 100).toFixed(1)}%`, pct: true };
  const abs = Math.abs(value);
  const dec = abs >= 100 ? 1 : abs >= 1 ? 2 : 4;
  return { label, text: value.toFixed(dec), pct: false };
}
