/**
 * Base types for the TypeScript parser subsystem.
 *
 * These are direct ports of the Python models in
 * src/epochix/parsers/base.py and src/epochix/models.py.
 */

import type { Counter } from "../story/narratives.generated";

export type { Counter };

export interface RawMetric {
  seq: number;
  epoch: number | null;
  step: number | null;
  key: string;
  value: number;
  parserName: string;
  confidence: number;
}

/**
 * Mutable parsing context shared across lines of a single run.
 *
 * The typed fields below are Python's `ctx.extra` bag: per-run state the
 * universal parser keeps between lines.
 */
export interface ParserContext {
  seq: number;
  currentEpoch: number | null;
  totalEpochs: number | null;
  currentStep: number | null;
  totalSteps: number | null;
  /** "iteration" once an `iter N` / `round N` counter has become the x-axis;
   *  "step" while a `step N` counter is, in a run that has printed no epoch;
   *  "epoch" once such a run prints one after all. */
  axis: "iteration" | "step" | "epoch" | null;
  /** First reading of each unrecognised name, held until the name recurs;
   *  null once it has been released. */
  heldUnrecognised: Map<string, RawMetric | null>;
  /** Lower-cased keys emitted so far (a printed CV mean suppresses the fold mean). */
  emittedKeys: Set<string>;
  /** Cross-validation folds by metric, and by parameter-search candidate. */
  cvFolds: Map<string, number[]>;
  cvCandidates: Map<string, Map<string, number[]>>;
  /** Lightning: the last complete "Epoch N" bar read, and its values. */
  plPrinted: number | null;
  plValues: string | null;
  /** Ultralytics: the post-training validation of best.pt has begun. */
  yoloFinalValidation: boolean;
  /** Boosting: the next round row reprints the best iteration. */
  boostingReprintNext: boolean;
  /** CatBoost: what its unnamed metric is called once its direction shows
   *  ("loss", "score", or "metric" when it never moved); the last eval value
   *  read; rows held (seq, round, values) until the direction is known. */
  catboostName: string | null;
  catboostLast: number | null;
  catboostHeld: Array<[number, number, Array<["val" | "train" | null, number | null, string, number]>]>;
  /** Keras: values already told for the current epoch (the finished bar is
   *  printed twice when there is validation data). */
  kerasTold: Map<string, string>;
  kerasToldEpoch: number | null;
  /** PyTorch example meters: the epoch (counted from 0) of the last training
   *  row, and that row's running top-1 accuracy, told with the validation
   *  result. */
  meterEpoch: number | null;
  meterTrainAccuracy: [string, number] | null;
  /** Step bar: the values last read off the bar, to tell a redraw from a reading. */
  stepBarValues: string | null;
  /** Set by a parser that puts something other than an epoch in
   *  `currentEpoch` — a boosting round, an iteration, a step — naming what it
   *  is. Cleared after every line: it says what THIS line counted by, so the
   *  kind belongs to whoever wrote the number last. Python's COUNTED_BY. */
  countedBy: Counter | null;
  /** Universal: inside pytest's report of a failing test (Python's
   *  extra["pytest_report"]). */
  pytestReport: boolean;
  /** Set by a parser that recognises a line as its own and reads no result
   *  from it; the engine then does not offer the line to the fallback
   *  parsers. Cleared after every line. Python's LINE_CLAIMED. */
  lineClaimed: boolean;
}

/** Mark the current line as recognised-but-empty; returns no metrics. */
export function claim(ctx: ParserContext): RawMetric[] {
  ctx.lineClaimed = true;
  return [];
}

export function makeContext(): ParserContext {
  return {
    seq: 0,
    currentEpoch: null,
    totalEpochs: null,
    currentStep: null,
    totalSteps: null,
    axis: null,
    heldUnrecognised: new Map(),
    emittedKeys: new Set(),
    cvFolds: new Map(),
    cvCandidates: new Map(),
    plPrinted: null,
    plValues: null,
    yoloFinalValidation: false,
    boostingReprintNext: false,
    catboostName: null,
    catboostLast: null,
    catboostHeld: [],
    kerasTold: new Map(),
    kerasToldEpoch: null,
    meterEpoch: null,
    meterTrainAccuracy: null,
    stepBarValues: null,
    countedBy: null,
    pytestReport: false,
    lineClaimed: false,
  };
}

/** Put `value` in the epoch slot and say what it counts. Python's count_by. */
export function countBy(ctx: ParserContext, counter: Counter, value: number): void {
  ctx.currentEpoch = value;
  ctx.countedBy = counter;
}

/**
 * What the epoch slot counts once a line has been read — Python's
 * counter_after. `before` is the slot as it stood before the line and
 * `current` what it counted then. A parser that wrote a round or a step said
 * so (countBy); one that moved the slot and said nothing wrote an epoch; a
 * line that left the slot alone changes nothing.
 */
export function counterAfter(
  ctx: ParserContext,
  before: number | null,
  current: Counter,
): Counter {
  const said = ctx.countedBy;
  ctx.countedBy = null;
  if (said !== null) return said;
  return ctx.currentEpoch !== before ? "epoch" : current;
}

/** Common interface every parser must implement. */
export interface Parser {
  readonly name: string;
  readonly priority: number;
  /** Return a 0.0–1.0 confidence that this parser matches the sample. */
  sniff(sampleLines: readonly string[]): number;
  /** Parse one line; mutates ctx; returns zero or more metrics. */
  parseLine(line: string, ctx: ParserContext): RawMetric[];
  /** Metrics that only exist once the stream ends (cross-validation means). */
  flush?(ctx: ParserContext): RawMetric[];
}
