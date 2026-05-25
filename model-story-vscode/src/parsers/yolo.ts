/**
 * TypeScript port of src/model_story/parsers/ultralytics_yolo.py
 */
import type { Parser, ParserContext, RawMetric } from "./base";

// Training row: "      1/50     1.23G   0.456   0.234   0.123   128"
const TRAIN_ROW =
  /^\s*(\d+)\/(\d+)\s+[\d.]+[GMK]?\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\d+/;

// Validation row: "all   5000   5000   0.712   0.654   0.678   0.432"
const VAL_ROW =
  /^\s*all\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/;

export class YoloParser implements Parser {
  readonly name = "ultralytics_yolo";
  readonly priority = 88;

  sniff(sampleLines: readonly string[]): number {
    const trainHits = sampleLines.filter((l) => TRAIN_ROW.test(l)).length;
    const valHits = sampleLines.filter((l) => VAL_ROW.test(l)).length;
    const score = (trainHits + valHits * 2) / Math.max(sampleLines.length, 1);
    return Math.min(score * 4, 0.94);
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    let m = TRAIN_ROW.exec(line);
    if (m) {
      ctx.currentEpoch = parseFloat(m[1]);
      ctx.totalEpochs = parseInt(m[2], 10);
      return [
        this._metric(ctx, "box_loss", parseFloat(m[3])),
        this._metric(ctx, "cls_loss", parseFloat(m[4])),
        this._metric(ctx, "dfl_loss", parseFloat(m[5])),
      ];
    }

    m = VAL_ROW.exec(line);
    if (m) {
      return [
        this._metric(ctx, "precision", parseFloat(m[1])),
        this._metric(ctx, "recall", parseFloat(m[2])),
        this._metric(ctx, "mAP50", parseFloat(m[3])),
        this._metric(ctx, "mAP", parseFloat(m[4])),
      ];
    }

    return [];
  }

  private _metric(ctx: ParserContext, key: string, value: number): RawMetric {
    return {
      seq: ctx.seq,
      epoch: ctx.currentEpoch,
      step: ctx.currentStep,
      key,
      value,
      parserName: this.name,
      confidence: 0.92,
    };
  }
}
