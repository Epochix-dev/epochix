/**
 * TypeScript port of src/epochix/parsers/stable_baselines3.py — the table
 * Stable-Baselines3 prints at `verbose=1`:
 *
 *   -----------------------------------------
 *   | rollout/                |             |
 *   |    ep_rew_mean          | 25.8        |
 *   | time/                   |             |
 *   |    iterations           | 2           |
 *   |    total_timesteps      | 4096        |
 *   -----------------------------------------
 *
 * A row with no value names a section, and the rows indented under it belong
 * to it (`rollout/ep_rew_mean`). The table is one write, so it is read whole:
 * every line is claimed, and its rows are handed over on the closing rule. A
 * table with `time/iterations` counts by iteration (PPO runs ten epochs over
 * each rollout, so an iteration is not an epoch); one without counts by step,
 * `time/total_timesteps`. The `time/` section and `train/n_updates` are
 * counters, not metrics. The rationale for each choice is in the Python file.
 */
import { claim, countBy, type Parser, type ParserContext, type RawMetric } from "./base";

const RULE = /^-{8,400}\s*$/;
const ROW = /^\| ( {3})?([^\s|][^|]{0,79}?) *\| ?([^|]{0,80}?) *\|\s*$/;
const SECTION = /^\| [a-z][\w-]{0,40}\/ *\| *\|\s*$/;

// Counted, not measured.
const COUNTERS = new Set(["train/n_updates"]);

/** Python's float(): the whole string a number, or null. */
function toNumber(raw: string): number | null {
  const s = raw.trim();
  if (!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$|^[-+]?(?:nan|inf(?:inity)?)$/i.test(s)) return null;
  const lower = s.toLowerCase().replace(/^\+/, "");
  if (lower.endsWith("nan")) return NaN;
  if (lower.endsWith("inf") || lower.endsWith("infinity")) return lower.startsWith("-") ? -Infinity : Infinity;
  return parseFloat(s);
}

export class StableBaselines3Parser implements Parser {
  readonly name = "stable_baselines3";
  readonly priority = 82;

  sniff(sampleLines: readonly string[]): number {
    const sections = sampleLines.filter((l) => SECTION.test(l)).length;
    const rules = sampleLines.filter((l) => RULE.test(l)).length;
    return sections >= 2 && rules >= 2 ? 0.92 : 0.0;
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const table = ctx.sb3Table;
    if (RULE.test(line)) {
      if (table === null) {
        ctx.sb3Table = new Map();
        ctx.sb3Section = "";
        return claim(ctx);
      }
      if (table.size === 0) return claim(ctx); // two rules in a row: still the opening one
      ctx.sb3Table = null;
      ctx.sb3Section = null;
      const told = this._close(table, ctx);
      return told.length > 0 ? told : claim(ctx);
    }

    if (table === null) return [];
    const row = ROW.exec(line);
    if (row === null) return [];
    const indented = row[1] !== undefined;
    const key = row[2];
    const raw = row[3];
    if (!indented && key.endsWith("/") && raw === "") {
      ctx.sb3Section = key;
      return claim(ctx);
    }
    const name = indented && ctx.sb3Section !== null ? `${ctx.sb3Section}${key}` : key;
    const value = toNumber(raw);
    if (value !== null) table.set(name, value); // a value that is not a number: nothing to read
    return claim(ctx);
  }

  private _close(table: ReadonlyMap<string, number>, ctx: ParserContext): RawMetric[] {
    const iterations = table.get("time/iterations");
    const steps = table.get("time/total_timesteps");
    if (steps !== undefined && Number.isFinite(steps)) ctx.currentStep = Math.trunc(steps);
    if (iterations !== undefined && Number.isFinite(iterations)) countBy(ctx, "iteration", iterations);
    else if (steps !== undefined && Number.isFinite(steps)) countBy(ctx, "step", steps);
    const out: RawMetric[] = [];
    for (const [key, value] of table) {
      if (key.startsWith("time/") || COUNTERS.has(key)) continue;
      out.push({
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key,
        value,
        parserName: this.name,
        confidence: 0.9,
      });
    }
    return out;
  }
}
