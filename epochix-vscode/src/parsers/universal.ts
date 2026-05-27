/**
 * TypeScript port of src/epochix/parsers/universal.py
 *
 * Three-pattern regex fallback: JSON fragments, key=value, key: value.
 */
import type { Parser, ParserContext, RawMetric } from "./base";

const KV_EQ = /(\w+)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const KV_COLON = /(\w+)\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const JSON_FRAG = /\{[^{}]+\}/g;

const EPOCH_KEYS = new Set(["epoch", "ep", "e"]);
const STEP_KEYS = new Set(["step", "iter", "iteration", "batch"]);
const SKIP_KEYS = new Set(["pid", "port", "seed", "rank", "world_size", "node"]);

export class UniversalParser implements Parser {
  readonly name = "universal";
  readonly priority = 1; // lowest — always a fallback

  sniff(_sampleLines: readonly string[]): number {
    return 0.10; // always weakly confident
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    const metrics: RawMetric[] = [];
    const seenKeys = new Set<string>();

    const add = (key: string, val: number, conf: number): void => {
      const keyLo = key.toLowerCase();
      if (seenKeys.has(keyLo) || SKIP_KEYS.has(keyLo)) return;
      seenKeys.add(keyLo);
      if (EPOCH_KEYS.has(keyLo)) {
        ctx.currentEpoch = val;
        return;
      }
      if (STEP_KEYS.has(keyLo)) {
        ctx.currentStep = Math.round(val);
        return;
      }
      metrics.push({
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key,
        value: val,
        parserName: this.name,
        confidence: conf,
      });
    };

    // Pattern 3 first: JSON fragments (highest confidence)
    JSON_FRAG.lastIndex = 0;
    let frag: RegExpExecArray | null;
    while ((frag = JSON_FRAG.exec(line)) !== null) {
      const text = frag[0].replace(/'/g, '"');
      try {
        const obj = JSON.parse(text) as Record<string, unknown>;
        for (const [k, v] of Object.entries(obj)) {
          if (typeof v === "number") add(k, v, 0.65);
        }
      } catch {
        // not valid JSON — skip
      }
    }

    // Pattern 1: key=value
    KV_EQ.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_EQ.exec(line)) !== null) {
      const v = parseFloat(kv[2]);
      if (!isNaN(v)) add(kv[1], v, 0.55);
    }

    // Pattern 2: key: value — lower confidence, more ambiguous
    KV_COLON.lastIndex = 0;
    while ((kv = KV_COLON.exec(line)) !== null) {
      const v = parseFloat(kv[2]);
      if (!isNaN(v)) add(kv[1], v, 0.45);
    }

    return metrics;
  }
}
