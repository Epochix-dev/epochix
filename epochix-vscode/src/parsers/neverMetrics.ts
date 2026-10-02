/**
 * Keys that are never a performance metric.
 *
 * Generated from `src/epochix/parsers/_never_metrics.py` (see
 * story/engineTables.generated.ts). It used to be a hand-kept copy, and each
 * parser once kept its own list, so a key filtered in one leaked through
 * another: the bundled demo's `Total params: 53,002` was charted as a flat
 * series worth 53.
 */
import { VALUE_DECIDES } from "../story/engineTables.generated";

export { NEVER_METRICS, VALUE_DECIDES } from "../story/engineTables.generated";

/**
 * Whether `key` (lower-cased) holding `value` is a setting, not a metric —
 * Python's `is_setting`. `precision` is the numeric precision in a Lightning
 * or AMP log (`precision=16`) and a classification metric in a training loop
 * (`precision=0.87`): a numeric precision is 16 or more, the metric cannot
 * exceed 1.
 */
export function isSetting(key: string, value: number): boolean {
  return VALUE_DECIDES.has(key) && !(value >= 0 && value <= 1);
}
