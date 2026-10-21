/**
 * TypeScript port of src/epochix/parsers/boosting.py.
 *
 * Gradient-boosting libraries print one row per boosting round, prefixed with
 * the round:
 *
 *     [0]  validation_0-logloss:0.51987  validation_1-logloss:0.52369   (XGBoost)
 *     [2]  valid_0's l2: 30497.7                                        (LightGBM)
 *     0:   learn: 0.6798710  test: 0.6801448  best: 0.6801448 (0)       (CatBoost)
 *
 * The universal parser cannot read them: its key pattern stops at the `-` in
 * `train-logloss`, so every eval set on the line collapsed to one key
 * (`logloss`), and because it keeps only the first occurrence of a key the
 * validation curve was dropped. The extension then graded the TRAINING loss —
 * the one curve that keeps improving while a model overfits — which is the
 * opposite of what a boosting log is worth reading for.
 *
 * The round number is the x-axis: not an epoch in the neural-network sense,
 * but structurally the same — one more unit of fitting.
 */
import { claim, type Parser, type ParserContext, type RawMetric } from "./base";
import { NEVER_METRICS, isSetting } from "./neverMetrics";

// Bounded quantifiers throughout: an unbounded run before a delimiter is
// O(n^2) on a long line. A name never starts inside a word or a number:
// CatBoost's timing tail, "total: 137ms<TAB>remaining: 8.11s", was read as a
// metric called "ms<TAB>remaining" on every row.
const ROUND = /^\s*(?:\[(\d{1,9})\]|(\d{1,9}):)\s/;
const PAIR =
  /(?<![\w.])([A-Za-z][\w'-]{0,48}(?:\s[A-Za-z][\w'-]{0,24})?)\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const DERIVED = new Set(["best", "bestiteration", "best_iteration", "remaining", "total", "elapsed"]);
// When training stops the libraries print the best round once more ("Early
// stopping, best iteration is:" / "Stopping. Best iteration:"); the row after
// it is a round already told, not a new measurement.
const BEST_ITERATION = /best iteration(?: is)?:\s*$/i;
// CatBoost's closing summary restates the best round: "bestTest = 0.99266",
// "bestIteration = 50". Values already told, not measurements.
const CATBOOST_SUMMARY = /^\s*best(?:Test|Iteration)\s*=/i;
// CatBoost names the split and never the metric: "0: test: 0.9790356" is the
// eval metric on the eval set, and nothing on the line says which metric or
// which way it runs. The running best beside it does: it follows the maximum
// of an AUC and the minimum of a loss. Until a row shows which, rows are held;
// a metric that has not moved in this many rounds is released under a name
// that claims no direction, so a live run is never held for good.
const CATBOOST_HOLD_ROUNDS = 10;
const UNNAMED = "";
const NUMBERED_SPLIT = /^([a-z]{1,16}?)(\d{1,3})$/;
const VALIDATION_TOKENS = ["validation", "valid", "eval", "test", "holdout", "dev"];
const TRAIN_TOKENS = ["training", "train", "learn", "fit"];

type Split = "val" | "train" | null;

/** (split, positional index, metric) for a name such as "validation_1-logloss". */
function dissect(name: string): [Split, number | null, string] {
  const cleaned = name.replace(/'s/g, " ").replace(/-/g, " ").replace(/\t/g, " ");
  const parts = cleaned.trim().split(/[\s_]+/).filter((p) => p.length > 0);
  if (parts.length === 0) return [null, null, name];

  const head = parts[0].toLowerCase();
  const digit = parts.slice(1).find((p) => /^\d+$/.test(p));
  const index = digit !== undefined ? parseInt(digit, 10) : null;
  const rest = parts.slice(1).filter((p) => !/^\d+$/.test(p));
  const isVal = VALIDATION_TOKENS.some((t) => head.startsWith(t));
  const isTrain = TRAIN_TOKENS.some((t) => head.startsWith(t));

  if (rest.length === 0) {
    // CatBoost prints the split alone: "learn: 0.67  test: 0.68". What the
    // metric is called depends on which way it runs (catboostName). A second
    // eval set is "test1", a third "test2": its position after the first.
    const numbered = NUMBERED_SPLIT.exec(head);
    const position = numbered !== null ? parseInt(numbered[2], 10) : index;
    if (isVal) return ["val", position, UNNAMED];
    if (isTrain) return ["train", position, UNNAMED];
    return [null, null, name];
  }
  const metric = rest.join("_").toLowerCase();
  if (isVal) return ["val", index, metric];
  if (isTrain) return ["train", index, metric];
  return [null, null, name];
}

/**
 * XGBoost's sklearn API names eval sets by position — validation_0,
 * validation_1 — and says nothing about which is which. `eval_set=[(X_train,
 * y_train), (X_test, y_test)]` is the ordering in its own documentation and
 * nearly every tutorial, so with several indexed sets the earliest is training
 * and the last is validation. A single set is validation (early stopping).
 * Names that say what they are ("valid_0", "learn", "test") are taken at
 * their word.
 */
function resolvePositions(
  found: Array<[Split, number | null, string, number]>,
): Array<[string, number]> {
  const byMetric = new Map<string, Array<[number | null, number]>>();
  const out: Array<[string, number]> = [];
  for (const [split, index, metric, value] of found) {
    if (split === "val" && index !== null) {
      const list = byMetric.get(metric) ?? [];
      list.push([index, value]);
      byMetric.set(metric, list);
    } else if (split !== null) {
      out.push([`${split}_${metric}`, value]);
    } else {
      out.push([metric, value]);
    }
  }
  for (const [metric, entries] of byMetric) {
    if (entries.length === 1) {
      out.push([`val_${metric}`, entries[0][1]]);
      continue;
    }
    const ordered = [...entries].sort((a, b) => (a[0] ?? 0) - (b[0] ?? 0));
    out.push([`train_${metric}`, ordered[0][1]]);
    out.push([`val_${metric}`, ordered[ordered.length - 1][1]]);
    for (const [idx, value] of ordered.slice(1, -1)) {
      out.push([`eval${idx ?? ""}_${metric}`, value]);
    }
  }
  return out;
}

/**
 * What CatBoost's unnamed metric is called once its direction shows: "loss"
 * when its running best follows the minimum, "score" when it follows the
 * maximum, null while a row cannot tell. A row equal to its best is a new
 * best, so a value that rose to get there is a score.
 */
function catboostName(test: number | null, best: number | null, last: number | null): string | null {
  if (test === null || best === null) return null;
  if (test !== best) return best > test ? "score" : "loss";
  if (last !== null && test !== last) return test > last ? "score" : "loss";
  return null;
}

type Row = Array<[Split, number | null, string, number]>;

/** Position of the last of CatBoost's eval sets on a row ("test" is 0). */
function lastEvalSet(found: Row): number | null {
  const positions = found.filter(([s, , mt]) => s === "val" && mt === UNNAMED).map(([, i]) => i ?? 0);
  return positions.length > 0 ? Math.max(...positions) : null;
}

/** The value CatBoost's running best follows: its last eval set's. */
function catboostValidation(found: Row): number | null {
  const last = lastEvalSet(found);
  return found.find(([s, i, mt]) => s === "val" && mt === UNNAMED && (i ?? 0) === last)?.[3] ?? null;
}

export class BoostingParser implements Parser {
  readonly name = "boosting";
  // Above universal, below the framework parsers — mirrors Python's ordering.
  readonly priority = 60;

  sniff(sampleLines: readonly string[]): number {
    let rows = 0;
    for (const line of sampleLines) {
      PAIR.lastIndex = 0;
      if (ROUND.test(line) && PAIR.test(line)) rows++;
    }
    PAIR.lastIndex = 0;
    if (rows >= 3) return 0.85;
    if (rows >= 1) return 0.40;
    return 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const m = ROUND.exec(line);
    if (m === null) {
      if (BEST_ITERATION.test(line)) ctx.boostingReprintNext = true;
      if (CATBOOST_SUMMARY.test(line)) return claim(ctx);
      return [];
    }
    if (ctx.boostingReprintNext) {
      ctx.boostingReprintNext = false;
      return claim(ctx);
    }
    const round = parseFloat(m[1] ?? m[2]);
    ctx.currentEpoch = round;
    ctx.currentStep = Math.round(round);

    const body = line.slice(m[0].length);
    const found: Row = [];
    let best: number | null = null;
    PAIR.lastIndex = 0;
    let pair: RegExpExecArray | null;
    while ((pair = PAIR.exec(body)) !== null) {
      const rawName = pair[1].trim();
      const value = parseFloat(pair[2]);
      if (Number.isNaN(value)) continue;
      const flat = rawName.replace(/[\s'-]/g, "").toLowerCase();
      if (flat === "best") {
        // Not charted, but it says which way CatBoost's unnamed metric runs.
        best = value;
        continue;
      }
      if (DERIVED.has(flat) || NEVER_METRICS.has(rawName.toLowerCase())) continue;
      if (isSetting(rawName.toLowerCase(), value)) continue;
      const [split, index, metric] = dissect(rawName);
      found.push([split, index, metric, value]);
    }

    if (found.some(([, , metric]) => metric === UNNAMED)) {
      return this.catboost(found, best, ctx, round);
    }
    return this.emit(resolvePositions(found), ctx.seq, round);
  }

  private catboost(found: Row, best: number | null, ctx: ParserContext, round: number): RawMetric[] {
    if (ctx.catboostName === null) {
      let name: string | null;
      if (best === null) {
        // No eval set: the only split is learn, the objective being minimised.
        name = "loss";
      } else {
        const test = catboostValidation(found);
        name = catboostName(test, best, ctx.catboostLast);
        ctx.catboostLast = test;
        if (name === null && ctx.catboostHeld.length + 1 < CATBOOST_HOLD_ROUNDS) {
          ctx.catboostHeld.push([ctx.seq, round, found]);
          return claim(ctx);
        }
      }
      ctx.catboostName = name ?? "metric";
    }
    const rows: Array<[number, number, Row]> = [...ctx.catboostHeld, [ctx.seq, round, found]];
    ctx.catboostHeld = [];
    const told = ctx.catboostName;
    return rows.flatMap(([seq, r, row]) => this.named(row, told, seq, r));
  }

  /** Release CatBoost rows still held when the log ends: their metric never
   *  moved, so they are told under a name that claims no direction. */
  flush(ctx: ParserContext): RawMetric[] {
    const rows = ctx.catboostHeld;
    ctx.catboostHeld = [];
    return rows.flatMap(([seq, r, row]) => this.named(row, "metric", seq, r));
  }

  private named(found: Row, name: string, seq: number, round: number): RawMetric[] {
    // CatBoost's eval sets are test, test1, test2...; its running best and
    // overfitting detector follow the last, so that one is the validation
    // curve and the others are told by position. Taken as XGBoost's
    // positional sets, the first would have been called training — and learn
    // already is.
    const last = lastEvalSet(found);
    const resolved: Array<[string, number]> = [];
    const others: Row = [];
    for (const [split, index, metric, value] of found) {
      if (metric !== UNNAMED) others.push([split, index, metric, value]);
      else if (split === "val" && (index ?? 0) !== last) resolved.push([`eval${index ?? 0}_${name}`, value]);
      else resolved.push([`${split}_${name}`, value]);
    }
    return this.emit([...resolved, ...resolvePositions(others)], seq, round);
  }

  private emit(resolved: Array<[string, number]>, seq: number, round: number): RawMetric[] {
    const metrics: RawMetric[] = [];
    const seen = new Set<string>();
    for (const [key, value] of resolved) {
      if (seen.has(key)) continue;
      seen.add(key);
      metrics.push({
        seq,
        epoch: round,
        step: Math.round(round),
        key,
        value,
        parserName: this.name,
        confidence: 0.80,
      });
    }
    return metrics;
  }
}

/** Exposed for tests. */
export const _internals = { dissect, resolvePositions, catboostName };
