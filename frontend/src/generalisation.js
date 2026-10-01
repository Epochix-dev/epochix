/**
 * generalisation.js — one reading of the train/validation gap.
 *
 * Two panels judged the same gap by two rules and neither looked at where
 * validation was heading. On a real ResNet-18 run (99.2% training accuracy,
 * 93.9% validation, validation loss at its lowest on the last epoch) the
 * diagnostics card said "Overfitting — it memorises training data more than it
 * learns" under a red ALERT, and the plain-English panel beside it said "a
 * small gap, so it learned the real patterns rather than just memorising".
 * Neither follows from the numbers: a gap alone shows neither memorising nor
 * its absence, and overfitting is validation getting WORSE while training
 * still improves.
 *
 * So the gap is read once, here, from three facts: how large it is, whether
 * validation is still at its best, and — if not — when it peaked.
 */

/** Accuracy gap (train − validation), as a fraction of 1. */
export const ACC_GAP_MODERATE = 0.05;
export const ACC_GAP_WIDE = 0.12;
/** Loss gap (validation − train) relative to the level of the two losses. */
export const LOSS_GAP_MODERATE = 0.18;
export const LOSS_GAP_WIDE = 0.45;
/** Validation counts as still at its best within this share of its best value. */
const AT_BEST_TOLERANCE = 0.01;
/** Fewer readings than this cannot say where validation is heading. */
const MIN_READINGS_FOR_TREND = 3;

/**
 * @typedef {object} GapReading
 * @property {'accuracy'|'loss'} kind       which pair of series it was read from
 * @property {number} train                 last training value
 * @property {number} val                   last validation value
 * @property {number} gap                   train − val (accuracy) or val − train (loss)
 * @property {number} rel                   the gap on the scale its bands use
 * @property {'small'|'moderate'|'wide'} size
 * @property {'at_best'|'past_best'|'unknown'} validation
 * @property {number|null} bestEpoch        epoch of validation's best, when past it
 * @property {'good'|'warn'|'bad'} status
 */

/**
 * Read the gap from a run's metric events, or null when no paired
 * train/validation series exists.
 * @param {Array<{canonical_key: string, value: number, epoch?: number}>} metrics
 * @returns {GapReading|null}
 */
export function readGap(metrics) {
  const acc = _series(metrics, 'accuracy');
  const valAcc = _series(metrics, 'val_accuracy');
  const trainLoss = _series(metrics, 'train_loss');
  const valLoss = _series(metrics, 'val_loss');

  let kind, train, val, gap, rel, size;
  if (acc.length && valAcc.length) {
    // Accuracy first: its gap is in points anyone can read, and a loss ratio
    // explodes as training loss nears zero (0.03 vs 0.20 is a factor of seven
    // on a run that is doing well).
    kind = 'accuracy';
    train = _last(acc);
    val = _last(valAcc);
    gap = train - val;
    rel = gap;
    size = gap > ACC_GAP_WIDE ? 'wide' : gap > ACC_GAP_MODERATE ? 'moderate' : 'small';
  } else if (trainLoss.length && valLoss.length) {
    kind = 'loss';
    train = _last(trainLoss);
    val = _last(valLoss);
    gap = val - train;
    const level = Math.max((Math.abs(train) + Math.abs(val)) / 2, 1e-6);
    rel = gap / level;
    size = rel > LOSS_GAP_WIDE ? 'wide' : rel > LOSS_GAP_MODERATE ? 'moderate' : 'small';
  } else {
    return null;
  }

  // Where validation is heading: loss when there is one (it moves before
  // accuracy does), accuracy otherwise.
  const { validation, bestEpoch } = valLoss.length
    ? _heading(valLoss, 'min')
    : _heading(valAcc, 'max');

  let status = 'good';
  if (size !== 'small') {
    if (validation === 'past_best') status = size === 'wide' ? 'bad' : 'warn';
    else if (validation === 'at_best') status = 'warn';
    else status = size === 'wide' ? 'bad' : 'warn';
  }
  return { kind, train, val, gap, rel, size, validation, bestEpoch, status };
}

/** Whether a validation series is still at its best, and when it peaked. */
function _heading(series, mode) {
  if (series.length < MIN_READINGS_FOR_TREND) return { validation: 'unknown', bestEpoch: null };
  let best = series[0];
  for (const p of series) {
    if (mode === 'min' ? p.value < best.value : p.value > best.value) best = p;
  }
  const last = series[series.length - 1];
  const slack = Math.abs(best.value) * AT_BEST_TOLERANCE;
  const worse = mode === 'min' ? last.value - best.value : best.value - last.value;
  if (worse <= slack) return { validation: 'at_best', bestEpoch: null };
  return { validation: 'past_best', bestEpoch: best.epoch };
}

function _series(metrics, key) {
  return (metrics ?? [])
    .filter((m) => m.canonical_key === key && Number.isFinite(m.value))
    .map((m) => ({ epoch: m.epoch ?? 0, value: m.value }))
    .sort((a, b) => a.epoch - b.epoch);
}

function _last(series) {
  return series[series.length - 1].value;
}
