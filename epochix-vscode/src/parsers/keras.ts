/**
 * TypeScript port of src/epochix/parsers/keras_tensorflow.py
 */
import { claim, type Parser, type ParserContext, type RawMetric } from "./base";
import { NEVER_METRICS } from "./neverMetrics";

const EPOCH_LINE = /^Epoch\s+(\d+)\/(\d+)\s*$/;
// A progress line, in each layout Keras has printed:
//   1563/1563 [==============================] - 10s 6ms/step - loss: 0.423 ...   (Keras 2)
//   43/43 ━━━━━━━━━━━━━━━━━━━━ 0s 6ms/step - accuracy: 0.9473 - loss: 0.2216 ...   (Keras 3)
//   43/43 - 0s - 5ms/step - accuracy: 0.9473 - loss: 0.2216 ...                    (verbose=2)
// Step counts bounded ({1,10}) so an unanchored search can't backtrack O(n²)
// on a long digit run (a 200k-digit line froze the sniff for seconds).
const METRIC_LINE = /\d{1,10}\/\d{1,10}\s+(?:\[=+>?\.*\]|━{2,}|-\s+\d{1,6}s\s+-)/;
// The step counter that opens a progress line: done/total.
const STEPS = /^\s*(\d{1,10})\/(\d{1,10})\s/;
// Keras prints every metric as " - name: value"; the dash is required, as
// in keras_tensorflow.py. Without it any "word: number" was a metric: the
// dataset sizes in "Train: 4200 | Val: 800", a tqdm "[00:12" as `00`.
const KV_PAIR = /(?:^|\s)-\s+([A-Za-z_]\w{0,63}):\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;

// Shared table — see neverMetrics.ts. A key filtered in one parser must
// not leak through another.
const SKIP_KEYS = NEVER_METRICS;

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

    // A bar caught mid-epoch is not the epoch's result. Written to a file,
    // Keras 3 puts every progress update on its own line, and each was read
    // as a reading.
    const steps = STEPS.exec(line);
    if (steps !== null && steps[1] !== steps[2]) return claim(ctx);

    // With validation data Keras 3 prints the finished bar twice — once when
    // training ends and again with the validation metrics added. The values
    // it repeats are one measurement, not two.
    if (ctx.kerasToldEpoch !== ctx.currentEpoch) {
      ctx.kerasTold = new Map();
      ctx.kerasToldEpoch = ctx.currentEpoch;
    }

    const metrics: RawMetric[] = [];
    KV_PAIR.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_PAIR.exec(line)) !== null) {
      const key = kv[1];
      if (SKIP_KEYS.has(key.toLowerCase())) continue;
      if (ctx.kerasTold.get(key) === kv[2]) continue;
      ctx.kerasTold.set(key, kv[2]);
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
    if (steps !== null && metrics.length === 0) return claim(ctx); // only repeated itself
    return metrics;
  }
}
