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
import type { Parser, ParserContext, RawMetric } from "./base";
import { NEVER_METRICS } from "./neverMetrics";

// Bounded quantifiers throughout: an unbounded run before a delimiter is
// O(n^2) on a long line.
const ROUND = /^\s*(?:\[(\d{1,9})\]|(\d{1,9}):)\s/;
const PAIR =
  /([A-Za-z][\w'-]{0,48}(?:\s[A-Za-z][\w'-]{0,24})?)\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const DERIVED = new Set(["best", "bestiteration", "best_iteration", "remaining", "total", "elapsed"]);
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
    // CatBoost prints the split alone: "learn: 0.67  test: 0.68".
    if (isVal) return ["val", index, "loss"];
    if (isTrain) return ["train", index, "loss"];
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
    if (m === null) return [];
    const round = parseFloat(m[1] ?? m[2]);
    ctx.currentEpoch = round;
    ctx.currentStep = Math.round(round);

    const body = line.slice(m[0].length);
    const found: Array<[Split, number | null, string, number]> = [];
    PAIR.lastIndex = 0;
    let pair: RegExpExecArray | null;
    while ((pair = PAIR.exec(body)) !== null) {
      const rawName = pair[1].trim();
      const value = parseFloat(pair[2]);
      if (Number.isNaN(value)) continue;
      const flat = rawName.replace(/[\s'-]/g, "").toLowerCase();
      if (DERIVED.has(flat) || NEVER_METRICS.has(rawName.toLowerCase())) continue;
      const [split, index, metric] = dissect(rawName);
      found.push([split, index, metric, value]);
    }

    const metrics: RawMetric[] = [];
    const seen = new Set<string>();
    for (const [key, value] of resolvePositions(found)) {
      if (seen.has(key)) continue;
      seen.add(key);
      metrics.push({
        seq: ctx.seq,
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
export const _internals = { dissect, resolvePositions };
