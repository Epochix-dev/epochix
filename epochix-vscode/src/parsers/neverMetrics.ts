/**
 * Keys that are never a performance metric.
 *
 * Generated from `src/epochix/parsers/_never_metrics.py` (see
 * story/engineTables.generated.ts). It used to be a hand-kept copy, and each
 * parser once kept its own list, so a key filtered in one leaked through
 * another: the bundled demo's `Total params: 53,002` was charted as a flat
 * series worth 53.
 */
export { NEVER_METRICS } from "../story/engineTables.generated";
