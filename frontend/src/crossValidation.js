/**
 * crossValidation.js — rank a run's cross-validation folds for the dashboard.
 *
 * Mirrors src/epochix/cross_validation.py `summarise`, which ranks the same
 * readings for `epochix check` and every export. Both are held to one fixture,
 * tests/fixtures/cv_ranking.json (generated from the Python function), so the
 * dashboard cannot name a different winner from the report beside it.
 *
 * The readings come from `run.config.cross_validation` (the server) or the
 * VS Code extension's engine: `{ folds: {metric: number[]}, candidates:
 * {setting: {metric: number[]}} }`.
 */

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

/** Sample standard deviation, as Python's statistics.stdev; null for one value. */
function stdev(xs) {
  if (xs.length < 2) return null;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
}

function row(metric, setting, values, chosen) {
  return {
    metric,
    setting,
    mean: mean(values),
    std: stdev(values),
    lowest: Math.min(...values),
    highest: Math.max(...values),
    folds: values.length,
    chosen,
  };
}

/** Whether these folds came from a search over more than one setting. */
export function isSearch(cv) {
  return Object.keys(cv?.candidates ?? {}).length > 1;
}

/**
 * Every setting's result per metric, best first within each metric.
 *
 * scikit-learn scorers are higher-is-better by construction (losses arrive
 * negated), so best is the highest mean; ties keep the order the log printed
 * them in. Metrics are in sorted order, as in Python.
 * @returns {Array<{metric:string, setting:string, mean:number, std:number|null,
 *   lowest:number, highest:number, folds:number, chosen:boolean}>}
 */
export function summarise(cv) {
  const folds = cv?.folds ?? {};
  const candidates = cv?.candidates ?? {};
  const settings = Object.keys(candidates);
  const search = settings.length > 1;
  const rows = [];
  for (const metric of Object.keys(folds).sort()) {
    if (settings.length > 0) {
      const ranked = settings
        .map((setting, order) => ({ setting, order, values: candidates[setting][metric] }))
        .filter((c) => Array.isArray(c.values) && c.values.length > 0)
        // Equal means keep log order — Python's sorted(reverse=True) is stable.
        // Python's fmean sums exactly and a JS sum can land one ulp off, so
        // means within 1e-12 count as the tie they are mathematically.
        .sort((a, b) => {
          const d = mean(b.values) - mean(a.values);
          return Math.abs(d) > 1e-12 ? d : a.order - b.order;
        });
      ranked.forEach((c, rank) => rows.push(row(metric, c.setting, c.values, search && rank === 0)));
    } else if ((folds[metric] ?? []).length >= 2) {
      rows.push(row(metric, '', folds[metric], false));
    }
  }
  return rows;
}
