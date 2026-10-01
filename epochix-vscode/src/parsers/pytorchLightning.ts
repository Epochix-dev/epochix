/**
 * TypeScript port of src/epochix/parsers/pytorch_lightning.py
 *
 * Two shapes of progress line.
 *
 * What Lightning itself prints (its tqdm bar; epochs count from 0, no total):
 *   Epoch 3: 100%|####| 148/148 [00:03<00:00, 38.67it/s, v_num=0, val_loss=1.660, val_acc=0.704]
 *
 * What a hand-written tqdm loop usually prints, and all this parser used to
 * accept — so a real Lightning log matched nothing, and the universal parser
 * skips progress bars by design: no metric, no frame, no story.
 *   Epoch 3/10: 100%|████| 250/250 [00:12<00:00, loss=0.432, acc=0.867]
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const EPOCH_HEADER = /Epoch\s+(\d{1,7})(?:\/(\d{1,7})|(?=:))/;
const PROGRESS_LINE = /Epoch\s+\d{1,7}(?:\/\d{1,7})?:.{0,400}\|/;
// "100%|#####| 148/148" — percent, done, total.
const BAR = /(\d{1,3})%\|[^|]{0,400}\|\s*(\d{1,12})\/(\d{1,12})/;
// The bar's own bracket: "[00:03<00:00, 38.67it/s, val_loss=1.660, ...]".
const POSTFIX = /\|\s*\d{1,12}\/\d{1,12}\s*\[([^\]]{0,2000})\]/;
const KV_PAIR = /(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
// Lines only Lightning prints. Its preamble and the validation bars between
// epochs outnumber the epoch lines, so counting epoch lines alone left a real
// log under the detection threshold.
const LIGHTNING_SIGN =
  /^GPU available: |^LOCAL_RANK: \d|\|\s*Name\s*\|\s*Type\s*\|\s*Params|^Validation DataLoader \d|`Trainer\.fit` stopped/;
const MAX_EPOCHS = /`max_epochs=(\d{1,7})` reached/;

// Not metrics: counters, tqdm's rate, the logger's version number, and the
// stopping condition Lightning appends to the last line.
const SKIP_KEYS = new Set(["epoch", "step", "it", "v_num", "max_epochs", "max_steps"]);

export class PytorchLightningParser implements Parser {
  readonly name = "pytorch_lightning";
  readonly priority = 90;

  sniff(sampleLines: readonly string[]): number {
    if (
      sampleLines.some((l) => LIGHTNING_SIGN.test(l)) &&
      sampleLines.some((l) => PROGRESS_LINE.test(l))
    ) {
      return 0.92;
    }
    const matches = sampleLines.filter((l) => PROGRESS_LINE.test(l)).length;
    return Math.min((matches / Math.max(sampleLines.length, 1)) * 3, 0.95);
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const header = EPOCH_HEADER.exec(line);
    if (!header) {
      // No epoch header: not a training-progress line. Config and trailer
      // lines ("`max_epochs=30` reached") are not metrics. As in Python.
      return [];
    }

    const printed = parseInt(header[1], 10);
    const handWritten = header[2] !== undefined;
    if (handWritten) ctx.totalEpochs = parseInt(header[2], 10);

    const bar = BAR.exec(line);
    const postfix = POSTFIX.exec(line);
    // Metrics live in the bar's bracket; anything after it is other output
    // that landed on the same line.
    const text = postfix ? postfix[1] : line;
    const pairs: Array<[string, string]> = [];
    KV_PAIR.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_PAIR.exec(text)) !== null) {
      if (!SKIP_KEYS.has(kv[1].toLowerCase())) pairs.push([kv[1], kv[2]]);
    }

    let epoch: number;
    if (handWritten) {
      epoch = printed;
    } else {
      if (bar !== null && bar[2] !== bar[3]) return []; // caught mid-epoch
      // Lightning's bar for epoch N carries the values logged at the end of
      // the epoch before it: validation runs after the bar reaches 100%. So
      // counted from 0 as printed, "Epoch N" shows epoch N-1's results —
      // which, counted from 1, is simply epoch N. The last epoch has no next
      // bar; Lightning redraws its own line once validation is done, so a
      // second complete "Epoch N" with different values is N+1.
      const values = JSON.stringify(pairs);
      if (ctx.plPrinted === printed) {
        if (ctx.plValues === values) return []; // the same line, drawn again
        epoch = printed + 1;
      } else {
        epoch = printed;
      }
      ctx.plPrinted = printed;
      ctx.plValues = values;
      const stopped = MAX_EPOCHS.exec(line);
      if (stopped) ctx.totalEpochs = parseInt(stopped[1], 10);
    }
    ctx.currentEpoch = epoch;

    const metrics: RawMetric[] = [];
    for (const [key, rawVal] of pairs) {
      const value = parseFloat(rawVal);
      if (!isNaN(value)) {
        metrics.push({
          seq: ctx.seq,
          epoch: ctx.currentEpoch,
          step: ctx.currentStep,
          key,
          value,
          parserName: this.name,
          confidence: 0.9,
        });
      }
    }
    return metrics;
  }
}
