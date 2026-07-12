/**
 * TypeScript port of src/epochix/parsers/pytorch_lightning.py
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const EPOCH_HEADER = /Epoch\s+(\d+)\/(\d+)/;
const KV_PAIR = /(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const PROGRESS_LINE = /Epoch\s+\d+\/\d+:.*\|/;

const SKIP_KEYS = new Set(["epoch", "step", "it"]);

export class PytorchLightningParser implements Parser {
  readonly name = "pytorch_lightning";
  readonly priority = 90;

  sniff(sampleLines: readonly string[]): number {
    const matches = sampleLines.filter((l) => PROGRESS_LINE.test(l)).length;
    return Math.min((matches / Math.max(sampleLines.length, 1)) * 3, 0.95);
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const epochMatch = EPOCH_HEADER.exec(line);
    if (epochMatch) {
      ctx.currentEpoch = parseFloat(epochMatch[1]);
      ctx.totalEpochs = parseInt(epochMatch[2], 10);
    }

    const metrics: RawMetric[] = [];
    if (!KV_PAIR.test(line)) {
      return metrics;
    }

    // Reset lastIndex since we used .test() above
    KV_PAIR.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_PAIR.exec(line)) !== null) {
      const key = kv[1];
      const rawVal = kv[2];
      if (SKIP_KEYS.has(key.toLowerCase())) {
        continue;
      }
      const value = parseFloat(rawVal);
      if (!isNaN(value)) {
        metrics.push({
          seq: ctx.seq,
          epoch: ctx.currentEpoch,
          step: ctx.currentStep,
          key,
          value,
          parserName: this.name,
          confidence: 0.90,
        });
      }
    }
    return metrics;
  }
}
