/**
 * Metric-name canonicalisation — Python's normalizer/canonical_keys.py, step
 * for step, over tables generated from it (engineTables.generated.ts).
 *
 * Shared by the parsers and the engine: the universal parser needs to know
 * whether a name is one we recognise before it will treat it as a metric.
 */
import {
  CANONICAL_MAP,
  SPLIT_PREFIXES,
  UNIT_SUFFIXES,
  VALIDATION_PREFIXES,
} from "./engineTables.generated";

const CANONICAL_NAMES: ReadonlySet<string> = new Set(CANONICAL_MAP.values());

function stripUnits(key: string): string {
  for (const suffix of UNIT_SUFFIXES) {
    if (key.endsWith(suffix) && key.length > suffix.length) return key.slice(0, -suffix.length);
  }
  return key;
}

/** The canonical name for `key`, or undefined when we do not know it. */
export function knownCanonical(key: string): string | undefined {
  const k = key.toLowerCase().trim();
  const direct = CANONICAL_MAP.get(k);
  if (direct !== undefined) return direct;
  const base = CANONICAL_MAP.get(stripUnits(k));
  if (base !== undefined) return base;
  for (const pre of SPLIT_PREFIXES) {
    if (k.startsWith(pre)) {
      const rest = stripUnits(k.slice(pre.length));
      const held = VALIDATION_PREFIXES.has(pre) ? CANONICAL_MAP.get(`val_${rest}`) : undefined;
      if (held !== undefined) return held;
      return CANONICAL_MAP.get(rest);
    }
  }
  return undefined;
}

/**
 * Canonical name for a raw metric key. An unknown key keeps its own name, as
 * in Python since 0.7.14: two metrics we do not recognise are two series.
 */
export function canonicalise(key: string): string {
  return knownCanonical(key) ?? key.trim();
}

/** Whether `key` is a metric we know by name, raw or canonical (is_recognised). */
export function isRecognised(key: string): boolean {
  return CANONICAL_NAMES.has(key) || knownCanonical(key) !== undefined;
}
