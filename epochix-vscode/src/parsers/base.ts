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
