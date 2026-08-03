/**
 * Parse a log file locally, then persist the run through the sidecar's public
 * API so it appears in saved history.
 *
 * The extension used to POST the file's *path* to `/api/parse` and let the
 * Python side read it. That endpoint never existed — the request 404'd, the
 * JSON body decoded fine, and the missing `run_id` surfaced as "could not
 * reach the Python engine", so every install silently ran standalone.
 *
 * Sending the parsed data instead of the path is also the better shape: the
 * extension already reads the file (that is what draws the chart), so the
 * server never needs a route that opens an arbitrary path on the host.
 */
import * as fs from "fs";
import * as readline from "readline";
import { StandaloneEngine } from "../webview/StandaloneEngine";
import type { ServerManager } from "./ServerManager";

/** Push events in bounded batches so a 2000-epoch log does not open 2000 sockets at once. */
const _CONCURRENCY = 8;

export async function persistLogFile(
  sidecar: ServerManager,
  filePath: string,
  runName: string,
): Promise<string> {
  const engine = new StandaloneEngine();

  await new Promise<void>((resolve, reject) => {
    const rl = readline.createInterface({
      input: fs.createReadStream(filePath, { encoding: "utf-8" }),
      crlfDelay: Infinity,
    });
    rl.on("line", (line) => void engine.feed(line + "\n"));
    rl.on("error", reject);
    rl.on("close", () => {
      engine.flush();
      engine.finish();
      resolve();
    });
  });

  const metrics = engine.metrics();
  if (metrics.length === 0) {
    throw new Error("no metrics found in this log");
  }

  // The dominant metric the frames actually measure. Without this the server
  // defaults `primary_metric` to "val_loss" while the frames carry accuracy,
  // and the learning curve then applies its lower-is-better inversion to
  // accuracy data — drawing a rising model as a falling line. The declared
  // metric and the values must agree; disagreeing is how the 123.6% bug
  // happened too.
  const counts = new Map<string, number>();
  for (const m of metrics) counts.set(m.canonical_key, (counts.get(m.canonical_key) ?? 0) + 1);
  const primary = engine.primaryMetricKey?.() ?? null;

  // Hand over the model summary too. The server no longer reads the file, so
  // this is the only route by which it can learn the architecture — without it
  // the Network State panel reads "No architecture to display" for a log that
  // plainly contains one.
  const runId = await sidecar.createRun(runName, undefined, engine.architecture(), primary);

  for (let i = 0; i < metrics.length; i += _CONCURRENCY) {
    await Promise.all(
      metrics.slice(i, i + _CONCURRENCY).map((m, j) =>
        sidecar.pushEvent(runId, {
          seq: i + j,
          epoch: m.epoch,
          canonical_key: m.canonical_key,
          // The engine has already normalised the key; the server keeps
          // raw_key for provenance, so echo it rather than invent one.
          raw_key: m.canonical_key,
          value: m.value,
        }),
      ),
    );
  }

  // Tell the server the log is over. It cannot distinguish "no more events"
  // from "the next one is slow", so without this the run keeps the running
  // spinner and never gets a final grade — every run persisted from here
  // showed up in `epochix list` as `⟳ [-] custom`, however good it was.
  //
  // Sent as its own zero-value event on the last seq rather than folded into
  // the loop above: the batch is dispatched with Promise.all, so whichever
  // request happens to finish last is not the one carrying the last metric.
  const last = metrics[metrics.length - 1];
  if (last) {
    await sidecar.pushEvent(runId, {
      seq: metrics.length,
      epoch: last.epoch,
      canonical_key: last.canonical_key,
      raw_key: last.canonical_key,
      value: last.value,
      finished: true,
    });
  }

  return runId;
}
