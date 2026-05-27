/**
 * TypeScript port of src/epochix/parsers/huggingface.py
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const HF_DICT_LINE = /^\s*\{['"]loss['"].*\}/;

export class HuggingFaceParser implements Parser {
  readonly name = "huggingface";
  readonly priority = 80;

  sniff(sampleLines: readonly string[]): number {
    const hits = sampleLines.filter((l) => HF_DICT_LINE.test(l)).length;
    return Math.min((hits / Math.max(sampleLines.length, 1)) * 5, 0.93);
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const stripped = line.trim();
    if (!stripped.startsWith("{")) return [];

    // Normalize Python dict literals to valid JSON
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

    const epoch = data["epoch"];
    if (epoch !== undefined && (typeof epoch === "number")) {
      ctx.currentEpoch = epoch;
      delete data["epoch"];
    }

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
        confidence: 0.91,
      });
    }
    return metrics;
  }
}
