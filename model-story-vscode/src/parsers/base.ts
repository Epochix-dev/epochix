/**
 * Base types for the TypeScript parser subsystem.
 *
 * These are direct ports of the Python models in
 * src/model_story/parsers/base.py and src/model_story/models.py.
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

/** Mutable parsing context shared across lines of a single run. */
export interface ParserContext {
  seq: number;
  currentEpoch: number | null;
  totalEpochs: number | null;
  currentStep: number | null;
  totalSteps: number | null;
}

export function makeContext(): ParserContext {
  return {
    seq: 0,
    currentEpoch: null,
    totalEpochs: null,
    currentStep: null,
    totalSteps: null,
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
}
