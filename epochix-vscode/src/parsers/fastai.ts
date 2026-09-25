/**
 * TypeScript port of src/epochix/parsers/fastai.py.
 *
 * fastai prints a table, one row per epoch, time last:
 *
 *     epoch  train_loss  valid_loss  accuracy  time
 *     0      0.681724    0.612903    0.671875  00:00
 *
 * The extension had no fastai parser, so the universal one read the time
 * column "00:00" as a metric named `00` and nothing else.
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const DATA_ROW =
  /^\s*(\d{1,9})\s+([\d.eE+-]{1,32})\s+([\d.eE+-]{1,32})\s+((?:[\d.eE+-]{1,32}\s+){0,64})?(\d{2}:\d{2})\s*$/;
const HEADER_LINE = /\btrain_loss\b.*\bvalid_loss\b/;

export class FastAIParser implements Parser {
  readonly name = "fastai";
  readonly priority = 75;
  private _extraHeaders: string[] = [];

  sniff(sampleLines: readonly string[]): number {
    const hasHeader = sampleLines.some((l) => HEADER_LINE.test(l));
    const hasData = sampleLines.some((l) => DATA_ROW.test(l));
    if (hasHeader && hasData) return 0.9;
    if (hasHeader || hasData) return 0.4;
    return 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    if (HEADER_LINE.test(line)) {
      // `epoch train_loss valid_loss <extras…> time`: extras start at index 3.
      const parts = line.trim().split(/\s+/);
      this._extraHeaders = parts.length > 4 ? parts.slice(3, -1) : [];
      return [];
    }
    const m = DATA_ROW.exec(line);
    if (m === null) return [];
    ctx.currentEpoch = parseFloat(m[1]);
    const metric = (key: string, value: number, confidence: number): RawMetric => ({
      seq: ctx.seq,
      epoch: ctx.currentEpoch,
      step: null,
      key,
      value,
      parserName: this.name,
      confidence,
    });
    const out: RawMetric[] = [
      metric("train_loss", parseFloat(m[2]), 0.88),
      metric("valid_loss", parseFloat(m[3]), 0.88),
    ];
    const extras = (m[4] ?? "").trim().split(/\s+/).filter((x) => x.length > 0);
    extras.forEach((raw, i) => {
      const value = parseFloat(raw);
      if (Number.isNaN(value)) return;
      // Validation metrics: fastai computes every column after valid_loss in
      // its validate step (as fastai.py).
      out.push(metric(`valid_${this._extraHeaders[i] ?? `metric_${i}`}`, value, 0.8));
    });
    return out.filter((x) => !Number.isNaN(x.value));
  }
}
