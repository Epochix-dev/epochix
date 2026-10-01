/**
 * Base types for the TypeScript parser subsystem.
 *
 * These are direct ports of the Python models in
 * src/epochix/parsers/base.py and src/epochix/models.py.
 */

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
  /** "iteration" once an `iter N` / `round N` counter has become the x-axis. */
  axis: "iteration" | null;
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
  /** Keras: values already told for the current epoch (the finished bar is
   *  printed twice when there is validation data). */
  kerasTold: Map<string, string>;
  kerasToldEpoch: number | null;
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
    kerasTold: new Map(),
    kerasToldEpoch: null,
    lineClaimed: false,
  };
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
