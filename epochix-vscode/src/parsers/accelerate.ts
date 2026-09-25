/**
 * TypeScript port of src/epochix/parsers/accelerate.py.
 *
 * `accelerator.print({...})` dicts keyed by step: {'loss': 0.61, 'step': 100}.
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const ACCEL_DICT = /^\s*\{['"](?:loss|eval_loss)['"].*['"]step['"]/;

export class AccelerateParser implements Parser {
  readonly name = "accelerate";
  readonly priority = 78;

  sniff(sampleLines: readonly string[]): number {
    const hits = sampleLines.filter((l) => ACCEL_DICT.test(l)).length;
    return Math.min((hits / Math.max(sampleLines.length, 1)) * 5, 0.88);
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const stripped = line.trim();
    if (!stripped.startsWith("{")) return [];
    const normalized = stripped
      .replace(/'/g, '"')
      .replace(/True/g, "true")
      .replace(/False/g, "false");
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(normalized) as Record<string, unknown>;
    } catch {
      return [];
    }
    if (data === null || typeof data !== "object") return [];
    const step = data["step"];
    delete data["step"];
    if (typeof step === "number") ctx.currentStep = Math.trunc(step);
    const epoch = data["epoch"];
    delete data["epoch"];
    if (typeof epoch === "number") ctx.currentEpoch = epoch;

    const metrics: RawMetric[] = [];
    for (const [key, val] of Object.entries(data)) {
      if (typeof val !== "number") continue;
      metrics.push({
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key,
        value: val,
        parserName: this.name,
        confidence: 0.85,
      });
    }
    return metrics;
  }
}
