/**
 * TypeScript port of src/epochix/parsers/huggingface.py
 *
 * HF Trainer logs a dict per logging step and per evaluation. Older versions
 * print the numbers bare; current ones (transformers 5) print them as strings:
 *   {'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}
 *   {'loss': '1.925', 'grad_norm': '2.584', 'learning_rate': '0.002707', 'epoch': '1'}
 * Only bare numbers were accepted, so a real log from a current version
 * produced no metric, no frame and no story.
 */
import { claim, type Parser, type ParserContext, type RawMetric } from "./base";
import { NEVER_METRICS } from "./neverMetrics";

const HF_DICT_LINE = /^\s*\{['"]loss['"].*\}/;
const NUMBER = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d{1,4})?$/;

// The dict the Trainer prints once, when training ends. Its `train_loss` is
// the average over the whole run, not a reading of the last epoch.
const SUMMARY_KEY = "train_runtime";

/** `value` as a number if it is one, bare or quoted; else null. */
function numberOf(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.length <= 40 && NUMBER.test(value.trim())) {
    return parseFloat(value);
  }
  return null;
}

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
      const parsed: unknown = JSON.parse(normalized);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return [];
      data = parsed as Record<string, unknown>;
    } catch {
      return [];
    }

    const epoch = numberOf(data["epoch"]);
    if (epoch !== null) ctx.currentEpoch = epoch;
    delete data["epoch"];
    // `step` is progress, not a metric (Accelerate prints the same dicts).
    const step = numberOf(data["step"]);
    if (step !== null) ctx.currentStep = Math.trunc(step);
    delete data["step"];

    if (SUMMARY_KEY in data) return claim(ctx);

    const metrics: RawMetric[] = [];
    for (const [key, val] of Object.entries(data)) {
      if (NEVER_METRICS.has(key.toLowerCase())) continue;
      const value = numberOf(val);
      if (value === null) continue;
      metrics.push({
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key,
        value,
        parserName: this.name,
        confidence: 0.91,
      });
    }
    return metrics;
  }
}
