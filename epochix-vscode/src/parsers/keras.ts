/**
 * TypeScript port of src/epochix/parsers/keras_tensorflow.py
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const EPOCH_LINE = /^Epoch\s+(\d+)\/(\d+)\s*$/;
const METRIC_LINE = /\d+\/\d+\s+\[=+>?\.*\]/;
const KV_PAIR = /(\w+):\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;

const SKIP_KEYS = new Set(["s", "ms", "us"]);

export class KerasParser implements Parser {
  readonly name = "keras_tensorflow";
  readonly priority = 85;

  sniff(sampleLines: readonly string[]): number {
    const hasEpoch = sampleLines.some((l) => EPOCH_LINE.test(l.trim()));
    const hasBar = sampleLines.some((l) => METRIC_LINE.test(l));
    if (hasEpoch && hasBar) return 0.92;
    if (hasEpoch || hasBar) return 0.45;
    return 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const epochMatch = EPOCH_LINE.exec(line.trim());
    if (epochMatch) {
      ctx.currentEpoch = parseFloat(epochMatch[1]);
      ctx.totalEpochs = parseInt(epochMatch[2], 10);
      return [];
    }

    const metrics: RawMetric[] = [];
    KV_PAIR.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_PAIR.exec(line)) !== null) {
      const key = kv[1];
      if (SKIP_KEYS.has(key.toLowerCase())) continue;
      const value = parseFloat(kv[2]);
      if (!isNaN(value)) {
        metrics.push({
          seq: ctx.seq,
          epoch: ctx.currentEpoch,
          step: ctx.currentStep,
          key,
          value,
          parserName: this.name,
          confidence: 0.88,
        });
      }
    }
    return metrics;
  }
}
