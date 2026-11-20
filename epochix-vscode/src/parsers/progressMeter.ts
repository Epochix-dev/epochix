/**
 * TypeScript port of src/epochix/parsers/progress_meter.py — the meters of
 * the PyTorch ImageNet example (pytorch/examples, imagenet/main.py):
 *
 *   Epoch: [0][ 1/32]<TAB>Time  0.845 ( 0.845)<TAB>Loss 7.1568e+00 (7.1568e+00)<TAB>Acc@1   0.00 (  0.00)
 *   Test: [ 1/10]<TAB>Time  0.182 ( 0.182)<TAB>Loss 3.7943e+00 (3.7943e+00)<TAB>Acc@1   0.00 (  0.00)
 *    *   Acc@1 10.333 Acc@5 64.667
 *
 * A training row gives the loss of its batch, at the fraction of the epoch
 * the row states; a `Test:` row is a validation pass caught part-way through
 * and is claimed; the ` *` line is the validation result, told at the number
 * of epochs finished, with the training accuracy of the epoch it follows (the
 * running average on that epoch's last row). `Acc@k` is a percentage by
 * construction and is read as a fraction here. The rationale for each choice
 * is in the Python file.
 */
import { claim, type Parser, type ParserContext, type RawMetric } from "./base";

const NUM = String.raw`[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?`;

const TRAIN_ROW = /^Epoch: \[(\d{1,7})\]\[\s*(\d{1,9})\/\s*(\d{1,9})\]\s/;
const TEST_ROW = /^Test: {0,2}\[\s*\d{1,9}\/\s*\d{1,9}\]\s/;
const SUMMARY = /^ \*\s/;
// "Loss 7.1568e+00 (7.1568e+00)" — a meter: name, value, (running average).
const METER = new RegExp(String.raw`(?<=\s)([A-Za-z][\w@]{0,31})\s+(${NUM})\s+\(\s*(${NUM})\)`, "g");
// "Acc@1 10.333" on the summary line — a meter's average alone.
const AVERAGE = new RegExp(String.raw`(?<=\s)([A-Za-z][\w@]{0,31})\s+(${NUM})(?=\s|$)`, "g");
const ACC_AT = /^acc@(\d{1,3})$/i;

// How long a batch took and how long its data took to load.
const TIMERS = new Set(["time", "data"]);

/** The k of a top-k accuracy meter (`Acc@5` -> "5"), or null. */
function topK(name: string): string | null {
  const top = ACC_AT.exec(name);
  return top !== null ? top[1] : null;
}

function value(name: string, raw: string): number {
  if (topK(name) === null) return parseFloat(raw);
  // "75.667" as 0.75667: read with the exponent rather than divided.
  return /e/i.test(raw) ? parseFloat(raw) / 100.0 : parseFloat(`${raw}e-2`);
}

export class ProgressMeterParser implements Parser {
  readonly name = "progress_meter";
  readonly priority = 80;

  sniff(sampleLines: readonly string[]): number {
    const rows = sampleLines.filter((l) => TRAIN_ROW.test(l) || TEST_ROW.test(l)).length;
    return rows >= 2 ? 0.9 : 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const row = TRAIN_ROW.exec(line);
    if (row !== null) {
      const epoch = parseInt(row[1], 10);
      const batch = parseInt(row[2], 10);
      const batches = parseInt(row[3], 10);
      ctx.meterEpoch = epoch;
      if (batches > 0) {
        ctx.currentEpoch = epoch + batch / batches;
        ctx.currentStep = epoch * batches + batch;
      }
      const readings: Array<[string, number]> = [];
      for (const m of line.matchAll(METER)) {
        const name = m[1];
        if (TIMERS.has(name.toLowerCase())) continue;
        const top = topK(name);
        if (top === null) readings.push([name, parseFloat(m[2])]);
        // The epoch so far; told with the validation result.
        else if (top === "1") ctx.meterTrainAccuracy = [name, value(name, m[3])];
      }
      return readings.length > 0 ? this._metrics(readings, ctx) : claim(ctx);
    }

    if (TEST_ROW.test(line)) return claim(ctx); // a validation pass caught part-way through

    if (SUMMARY.test(line)) {
      if (ctx.meterEpoch !== null) ctx.currentEpoch = ctx.meterEpoch + 1;
      const readings: Array<[string, number]> = [];
      for (const m of line.matchAll(AVERAGE)) {
        if (!TIMERS.has(m[1].toLowerCase())) readings.push([`val_${m[1]}`, value(m[1], m[2])]);
      }
      const kept = ctx.meterTrainAccuracy;
      ctx.meterTrainAccuracy = null;
      if (readings.length > 0 && kept !== null) readings.push(kept);
      return readings.length > 0 ? this._metrics(readings, ctx) : claim(ctx);
    }

    return [];
  }

  private _metrics(readings: ReadonlyArray<[string, number]>, ctx: ParserContext): RawMetric[] {
    return readings.map(([key, v]) => ({
      seq: ctx.seq,
      epoch: ctx.currentEpoch,
      step: ctx.currentStep,
      key,
      value: v,
      parserName: this.name,
      confidence: 0.88,
    }));
  }
}
