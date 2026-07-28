/**
 * Keys that are never a performance metric — the TypeScript half.
 *
 * Mirrors `src/epochix/parsers/_never_metrics.py`. Each parser used to keep its
 * own skip list, so a key filtered in one leaked through another: the bundled
 * demo's `Total params: 53,002` was charted as a flat series worth **53**,
 * because the comma truncated it and no TS parser knew the key.
 *
 * **Keep this in sync with the Python table.** Parser fixes that land on one
 * side and not the other have reintroduced already-fixed bugs before.
 */

/** Totals printed by a model summary. Comma-grouped, so often mis-parsed too. */
export const MODEL_SUMMARY_KEYS = [
  "params",
  "total_params",
  "trainable_params",
  "non_trainable_params",
  "flops",
  "macs",
];

/** Run configuration: constant for the run, so it charts as a flat line. */
export const CONFIG_KEYS = [
  "batch_size",
  "batchsize",
  "bs",
  "num_workers",
  "workers",
  "img_size",
  "imgsz",
  "epochs",
  "num_epochs",
  "max_epochs",
  "total_epochs",
  "gpus",
  "devices",
  "precision",
  "accumulate_grad_batches",
  "log_every_n_steps",
  "save_top_k",
  "patience",
  "verbose",
  "seed",
  "pid",
  "port",
  "rank",
  "world_size",
  "node",
];

/** Units that appear as `key: value` in progress lines ("32ms/step"). */
export const UNIT_KEYS = ["s", "ms", "us", "ns"];

export const NEVER_METRICS = new Set([
  ...MODEL_SUMMARY_KEYS,
  ...CONFIG_KEYS,
  ...UNIT_KEYS,
]);
