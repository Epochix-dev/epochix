/**
 * TypeScript port of src/epochix/parsers/universal.py
 *
 * Three-pattern regex fallback: JSON fragments, key=value, key: value.
 */
import type { Parser, ParserContext, RawMetric } from "./base";

// Key capture bounded ({1,64}) to prevent O(n²) regex backtracking on a long
// word-character run before a missing delimiter (a 100k-char line hung the
// parser for seconds). A real metric key is never that long.
const KV_EQ = /(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const KV_COLON = /(\w{1,64})\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
const JSON_FRAG = /\{[^{}]+\}/g;

// Bare "Epoch N" / "Epoch N/M" header — the epoch printed on its own or on the
// same line as the metrics, with no key=value form. Without this the extension
// showed "Epoch —" and a dead progress bar for every log that fell back to the
// universal parser (the Python parser gained this in 0.5.8; the port lagged).
const EPOCH_HEADER = /\bepoch\s+(\d{1,9})(?:\s*\/\s*(\d{1,9}))?\b/i;

const EPOCH_KEYS = new Set(["epoch", "ep", "e"]);
const STEP_KEYS = new Set(["step", "iter", "iteration", "batch"]);
const SKIP_KEYS = new Set(["pid", "port", "seed", "rank", "world_size", "node"]);

interface Candidate {
  key: string;
  value: number;
  confidence: number;
}

export class UniversalParser implements Parser {
  readonly name = "universal";
  readonly priority = 1; // lowest — always a fallback

  sniff(_sampleLines: readonly string[]): number {
    return 0.10; // always weakly confident
  }

  parseLine(line: string, ctx: ParserContext): RawMetric[] {
    // Bare epoch header ("Epoch 1/8: …") — set the epoch and total so metrics
    // on this line are stamped with it and the progress bar advances.
    const header = EPOCH_HEADER.exec(line);
    if (header) {
      ctx.currentEpoch = parseFloat(header[1]);
      if (header[2] !== undefined) ctx.totalEpochs = parseInt(header[2], 10);
    }

    // Collect every candidate first, in confidence order.
    const candidates: Candidate[] = [];

    JSON_FRAG.lastIndex = 0;
    let frag: RegExpExecArray | null;
    while ((frag = JSON_FRAG.exec(line)) !== null) {
      const text = frag[0].replace(/'/g, '"');
      try {
        const obj = JSON.parse(text) as Record<string, unknown>;
        for (const [k, v] of Object.entries(obj)) {
          if (typeof v === "number") candidates.push({ key: k, value: v, confidence: 0.65 });
        }
      } catch {
        // not valid JSON — skip
      }
    }

    KV_EQ.lastIndex = 0;
    let kv: RegExpExecArray | null;
    while ((kv = KV_EQ.exec(line)) !== null) {
      const v = parseFloat(kv[2]);
      if (!isNaN(v)) candidates.push({ key: kv[1], value: v, confidence: 0.55 });
    }

    KV_COLON.lastIndex = 0;
    while ((kv = KV_COLON.exec(line)) !== null) {
      const v = parseFloat(kv[2]);
      if (!isNaN(v)) candidates.push({ key: kv[1], value: v, confidence: 0.45 });
    }

    // Pass 1 — control keys (epoch/step) take effect BEFORE any metric on this
    // line is stamped. They can legitimately come last ("loss=0.3 epoch=3"),
    // and stamping as we scanned attributed those metrics to the PREVIOUS epoch
    // (and lost epoch 0 entirely). Ported from the Python fix in 0.5.12.
    const claimed = new Set<string>();
    for (const c of candidates) {
      const keyLo = c.key.toLowerCase();
      if (claimed.has(keyLo)) continue;
      if (EPOCH_KEYS.has(keyLo)) {
        claimed.add(keyLo);
        ctx.currentEpoch = c.value;
      } else if (STEP_KEYS.has(keyLo)) {
        claimed.add(keyLo);
        ctx.currentStep = Math.round(c.value);
      }
    }

    // Pass 2 — emit the metrics; first occurrence of a key wins.
    const metrics: RawMetric[] = [];
    const seenKeys = new Set<string>();
    for (const c of candidates) {
      const keyLo = c.key.toLowerCase();
      if (
        seenKeys.has(keyLo) ||
        SKIP_KEYS.has(keyLo) ||
        EPOCH_KEYS.has(keyLo) ||
        STEP_KEYS.has(keyLo)
      ) {
        continue;
      }
      seenKeys.add(keyLo);
      metrics.push({
        seq: ctx.seq,
        epoch: ctx.currentEpoch,
        step: ctx.currentStep,
        key: c.key,
        value: c.value,
        parserName: this.name,
        confidence: c.confidence,
      });
    }

    return metrics;
  }
}
