/**
 * TypeScript port of src/epochix/parsers/universal.py — pattern for pattern.
 *
 * The earlier port had three of its patterns and none of its guards, so the
 * extension read a tqdm "[00:12<00:00" as a metric named `00`, a Lightning
 * banner's "using: 0" as a metric named `using`, and a dataset line's
 * "Train: 4200" as a result. The rationale for each pattern is in the Python
 * file; comments here note only what is specific to the port.
 *
 * Every quantifier is bounded: an unbounded run before a delimiter is O(n^2)
 * on a long line (AGENTS.md).
 */
import type { Parser, ParserContext, RawMetric } from "./base";
import { isRecognised } from "../story/canonical";
import { NEVER_METRICS, NN_REPR_KWARGS } from "../story/engineTables.generated";

const NUM = String.raw`[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?`;

const KV_EQ = new RegExp(String.raw`([A-Za-z_]\w{0,63})\s*=\s*(${NUM})`, "g");
const KV_COLON = new RegExp(String.raw`([A-Za-z_]\w{0,63})\s*:\s*(${NUM})`, "g");
const JSON_FRAG = /\{[^{}]+\}/g;
const EPOCH_HEADER = /\bepoch\s+(\d{1,9})(?:\s*\/\s*(\d{1,9}))?\b/i;
const KV_SPACE = new RegExp(String.raw`\b([A-Za-z]\w{0,63})\s+(${NUM})(?=\s|$)`, "g");
const ROW_LEADER = /^\s*(?:epoch|ep|iter|iteration|step|batch|round)\s+\d{1,9}\b/i;
const ITERATION_LEADER = /^\s*(?:iter|iteration|round)\s+(\d{1,9})\b/i;
const QUALIFIED = new RegExp(
  String.raw`\b(train|training|test|val|valid|validation|eval|holdout)\s+(\w{1,64})\s*[:=]\s*(${NUM})`,
  "gi",
);
const VAL_WORDS = new Set(["test", "val", "valid", "validation", "eval", "holdout"]);
const COMPOUND = new RegExp(String.raw`\b([A-Za-z]\w{0,31})[\s_]+(\w{1,32})\s*[:=]\s*(${NUM})`, "g");
const CONSTRUCTOR = /\b[A-Z]\w*\((?:[^()]|\([^()]*\))*\)/g;

const FOLD_ROW = /^\s*(?:\[cv(?:\s+\d+\s*\/\s*\d+)?\]|fold\s+\d+\b)/i;
const CV_SCORE = new RegExp(String.raw`\bscore\s*[:=]\s*\(?\s*(?:test|train)?\s*=?\s*(${NUM})`, "i");
const CV_NAMED_SCORE = new RegExp(String.raw`(\w{1,32})\s*:\s*\(\s*(?:test|train)\s*=\s*(${NUM})\s*\)`, "gi");
const CV_PARAMS = /^\s*\[cv[^\]]*\]\s+END\s+\.*(.*?);/i;

const EPOCH_KEYS = new Set(["epoch", "ep", "e"]);
const STEP_KEYS = new Set(["step", "iter", "iteration", "batch"]);
const SKIP_KEYS = new Set([...NEVER_METRICS, ...NN_REPR_KWARGS]);
const PROGRESS_BAR = /\d{1,3}%\|/;

type Span = [number, number];

function blanked(text: string, spans: readonly Span[]): string {
  if (spans.length === 0) return text;
  let out = "";
  let at = 0;
  for (const [start, end] of spans) {
    out += text.slice(at, start) + " ".repeat(end - start);
    at = end;
  }
  return out + text.slice(at);
}

function spanOf(m: RegExpMatchArray): Span {
  const start = m.index ?? 0;
  return [start, start + m[0].length];
}

function mean(values: readonly number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export class UniversalParser implements Parser {
  readonly name = "universal";
  readonly priority = 1; // lowest — always a fallback

  sniff(_sampleLines: readonly string[]): number {
    return 0.1; // always weakly confident; the detector uses this as its floor
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    if (line.includes("%|") && PROGRESS_BAR.test(line)) return [];

    if (FOLD_ROW.test(line)) {
      this._collectFold(line, ctx);
      return [];
    }

    const eh = EPOCH_HEADER.exec(line);
    if (eh !== null) {
      ctx.currentEpoch = parseFloat(eh[1]);
      if (eh[2] !== undefined) ctx.totalEpochs = parseInt(eh[2], 10);
    }

    const it = ITERATION_LEADER.exec(line);
    if (it !== null && (ctx.currentEpoch === null || ctx.axis === "iteration")) {
      ctx.axis = "iteration";
      ctx.currentEpoch = parseFloat(it[1]);
    }

    let text = line.includes("(") ? line.replace(CONSTRUCTOR, (m) => " ".repeat(m.length)) : line;
    const delimited = text.includes("=") || text.includes(":");
    const candidates: Array<[string, number, number]> = [];

    let spans: Span[] = [];
    if (delimited) {
      for (const q of text.matchAll(QUALIFIED)) {
        spans.push(spanOf(q));
        const split = VAL_WORDS.has(q[1].toLowerCase()) ? "val" : "train";
        const v = parseFloat(q[3]);
        if (!Number.isNaN(v)) candidates.push([`${split}_${q[2]}`, v, 0.6]);
      }
    }
    text = blanked(text, spans);

    if (delimited) {
      const source = text;
      for (const c of source.matchAll(COMPOUND)) {
        const joined = `${c[1]}_${c[2]}`;
        if (!isRecognised(joined)) continue;
        const v = parseFloat(c[3]);
        if (!Number.isNaN(v)) candidates.push([joined, v, 0.58]);
        const [start, end] = spanOf(c);
        text = text.slice(0, start) + " ".repeat(end - start) + text.slice(end);
      }
    }

    spans = [];
    if (text.includes("{")) {
      for (const frag of text.matchAll(JSON_FRAG)) {
        spans.push(spanOf(frag));
        let obj: unknown;
        try {
          obj = JSON.parse(frag[0].replace(/'/g, '"'));
        } catch {
          continue;
        }
        if (obj === null || typeof obj !== "object") continue;
        for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
          if (typeof v === "number") candidates.push([k, v, 0.65]);
        }
      }
    }
    text = blanked(text, spans);

    spans = [];
    if (text.includes("=")) {
      for (const m of text.matchAll(KV_EQ)) {
        spans.push(spanOf(m));
        const v = parseFloat(m[2]);
        if (!Number.isNaN(v)) candidates.push([m[1], v, 0.55]);
      }
    }
    text = blanked(text, spans);

    spans = [];
    if (text.includes(":")) {
      for (const m of text.matchAll(KV_COLON)) {
        spans.push(spanOf(m));
        const v = parseFloat(m[2]);
        if (!Number.isNaN(v)) candidates.push([m[1], v, 0.45]);
      }
    }
    text = blanked(text, spans);

    if (ROW_LEADER.test(line)) {
      for (const m of text.matchAll(KV_SPACE)) {
        const key = m[1];
        const lo = key.toLowerCase();
        if (!EPOCH_KEYS.has(lo) && !STEP_KEYS.has(lo) && !isRecognised(key)) continue;
        const v = parseFloat(m[2]);
        if (!Number.isNaN(v)) candidates.push([key, v, 0.5]);
      }
    }

    // Pass 1 — control keys first, so metrics on this line are stamped with them.
    const claimed = new Set<string>();
    for (const [key, val] of candidates) {
      const lo = key.toLowerCase();
      if (claimed.has(lo)) continue;
      if (EPOCH_KEYS.has(lo)) {
        claimed.add(lo);
        ctx.currentEpoch = val;
      } else if (STEP_KEYS.has(lo)) {
        claimed.add(lo);
        ctx.currentStep = Math.trunc(val);
      }
    }

    // Pass 2 — emit; first occurrence of a key wins.
    const metrics: RawMetric[] = [];
    const seen = new Set<string>();
    for (const [key, val, conf] of candidates) {
      const lo = key.toLowerCase();
      if (seen.has(lo) || SKIP_KEYS.has(lo) || EPOCH_KEYS.has(lo) || STEP_KEYS.has(lo)) continue;
      seen.add(lo);
      const metric: RawMetric = {
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key,
        value: val,
        parserName: this.name,
        confidence: conf,
      };
      // An unrecognised name printed once is indistinguishable from prose;
      // hold it until it recurs (see universal.py).
      if (!isRecognised(key)) {
        if (!ctx.heldUnrecognised.has(lo)) {
          ctx.heldUnrecognised.set(lo, metric);
          continue;
        }
        const first = ctx.heldUnrecognised.get(lo);
        if (first) {
          metrics.push(first);
          ctx.heldUnrecognised.set(lo, null);
        }
      }
      ctx.emittedKeys.add(lo);
      metrics.push(metric);
    }
    return metrics;
  }

  flush(ctx: ParserContext): RawMetric[] {
    const out: RawMetric[] = [];
    for (const [key, allFolds] of ctx.cvFolds) {
      if (allFolds.length < 2 || ctx.emittedKeys.has(key.toLowerCase())) continue;
      let values = allFolds;
      if (ctx.cvCandidates.size > 1) {
        const scored = [...ctx.cvCandidates.values()]
          .map((c) => c.get(key))
          .filter((v): v is number[] => v !== undefined);
        if (scored.length > 0) {
          values = scored.reduce((best, v) => (mean(v) > mean(best) ? v : best));
        }
      }
      out.push({
        seq: ctx.seq,
        epoch: null,
        step: null,
        key,
        value: mean(values),
        parserName: this.name,
        confidence: 0.5,
      });
    }
    return out;
  }

  private _collectFold(line: string, ctx: ParserContext): void {
    const readings = this._foldReadings(line);
    if (readings.length === 0) return;
    for (const [key, value] of readings) {
      const list = ctx.cvFolds.get(key) ?? [];
      list.push(value);
      ctx.cvFolds.set(key, list);
    }
    const params = CV_PARAMS.exec(line);
    const label = params ? params[1].trim().replace(/,+$/, "").trim() : "";
    if (!label) return;
    const byKey = ctx.cvCandidates.get(label) ?? new Map<string, number[]>();
    for (const [key, value] of readings) {
      const list = byKey.get(key) ?? [];
      list.push(value);
      byKey.set(key, list);
    }
    ctx.cvCandidates.set(label, byKey);
  }

  private _foldReadings(line: string): Array<[string, number]> {
    const named = [...line.matchAll(CV_NAMED_SCORE)];
    if (named.length > 0) {
      return named
        .map((m): [string, number] => [m[1], parseFloat(m[2])])
        .filter(([, v]) => !Number.isNaN(v));
    }
    const score = CV_SCORE.exec(line);
    if (score !== null) {
      const v = parseFloat(score[1]);
      return Number.isNaN(v) ? [] : [["score", v]];
    }
    for (const pattern of [KV_EQ, KV_COLON]) {
      const hits: Array<[string, number]> = [];
      for (const m of line.matchAll(pattern)) {
        const lo = m[1].toLowerCase();
        if (SKIP_KEYS.has(lo) || EPOCH_KEYS.has(lo) || STEP_KEYS.has(lo)) continue;
        const v = parseFloat(m[2]);
        if (!Number.isNaN(v)) hits.push([m[1], v]);
      }
      if (hits.length > 0) return hits;
    }
    return [];
  }
}
