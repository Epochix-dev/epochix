/**
 * TypeScript port of src/epochix/parsers/step_bar.py — one tqdm bar for the
 * whole run, counting steps, as diffusers' LoRA and DreamBooth scripts draw:
 *
 *   Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]
 *
 * The bar is redrawn in place, twice a step: once when the counter moves on,
 * still carrying the values of the step before, and again when the new values
 * are set. A redraw is a reading when its values differ from the last ones
 * read, told at the step the bar stands at; any other redraw is claimed. The
 * step is the run's x-axis and the bar's total its length. The rationale is
 * in the Python file.
 */
import { claim, type Parser, type ParserContext, type RawMetric } from "./base";
import { isSetting } from "./neverMetrics";
import { NEVER_METRICS } from "../story/engineTables.generated";

const NUM = String.raw`[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?`;

// Percent, the bar, done/total, and tqdm's bracket.
const BAR = /^\s*steps:\s{1,8}\d{1,3}%\|[^|]{0,400}\|\s*(\d{1,12})\/(\d{1,12})\s*\[([^\]]{0,2000})\]/i;
// Cheap to test on every carriage-return segment of every line.
const BAR_START = /^\s*steps:\s{1,8}\d{1,3}%\|/i;
const PAIR = String.raw`(?<![\w.])([A-Za-z_]\w{0,63})=(${NUM})(?=[,\s]|$)`;
const KV_PAIR = new RegExp(PAIR, "g");
const ANY_PAIR = new RegExp(PAIR);

/**
 * The redraws of a run-long step bar held in one line, or null — Python's
 * step_bar_redraws. `text` is a line as it was written, carriage returns
 * included; its final state comes last, whatever it is.
 */
export function stepBarRedraws(text: string): string[] | null {
  if (!text.includes("\r")) return null;
  const segments = text.split("\r");
  const bars = segments.slice(0, -1).filter((s) => BAR_START.test(s));
  if (bars.length === 0) return null;
  return [...bars, segments[segments.length - 1]];
}

/** Whether `text` opens as a run-long step bar does. */
export function isStepBar(text: string): boolean {
  return BAR_START.test(text);
}

function pairs(bracket: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const m of bracket.matchAll(KV_PAIR)) {
    if (!NEVER_METRICS.has(m[1].toLowerCase())) out.push([m[1], m[2]]);
  }
  return out;
}

export class StepBarParser implements Parser {
  readonly name = "step_bar";
  readonly priority = 82;

  sniff(sampleLines: readonly string[]): number {
    let told = 0;
    for (const line of sampleLines) {
      const bar = BAR.exec(line);
      if (bar !== null && ANY_PAIR.test(bar[3])) {
        told++;
        if (told >= 2) return 0.9;
      }
    }
    return 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const bar = BAR.exec(line);
    if (bar === null) return [];
    const values = pairs(bar[3]);
    const drawn = JSON.stringify(values);
    if (values.length === 0 || ctx.stepBarValues === drawn) return claim(ctx);
    ctx.stepBarValues = drawn;

    const step = parseInt(bar[1], 10);
    const total = parseInt(bar[2], 10);
    ctx.currentStep = step;
    ctx.currentEpoch = step;
    if (total > 0) ctx.totalEpochs = total;

    const metrics: RawMetric[] = [];
    for (const [key, raw] of values) {
      const value = parseFloat(raw);
      if (isSetting(key.toLowerCase(), value)) continue;
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
    return metrics.length > 0 ? metrics : claim(ctx);
  }
}
