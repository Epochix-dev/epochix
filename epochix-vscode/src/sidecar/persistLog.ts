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
import { taskHint } from "../config";
import { StandaloneEngine } from "../webview/StandaloneEngine";
import type { ServerManager } from "./ServerManager";

/** Push events in bounded batches so a 2000-epoch log does not open 2000 sockets at once. */
const _CONCURRENCY = 8;

export async function persistLogFile(
  sidecar: ServerManager,
  filePath: string,
  runName: string,
  locale?: string,
): Promise<string> {
  const hint = taskHint();
  const engine = new StandaloneEngine(hint, locale);

  await new Promise<void>((resolve, reject) => {
    // Raw chunks, not readline: readline ends a line at a lone \r too, so every
    // progress-bar redraw ("\r 1/3 ... 0%\r 1/3 ... 100%") became its own line
    // and a YOLO epoch was recorded once per redraw. The engine splits on \n
    // and collapses redraws to their final state, as the Python ingester does.
    const stream = fs.createReadStream(filePath, { encoding: "utf-8" });
    stream.on("data", (chunk) => void engine.feed(String(chunk)));
    stream.on("error", reject);
    stream.on("end", () => {
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
  const runId = await sidecar.createRun(runName, hint, engine.architecture(), primary, locale);

  // Every metric but the last goes in parallel batches; the last is sent on
  // its own afterwards, carrying `finished` (see below).
  const body = metrics.slice(0, -1);
  for (let i = 0; i < body.length; i += _CONCURRENCY) {
    await Promise.all(
      body.slice(i, i + _CONCURRENCY).map((m, j) =>
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
  // The flag rides on the real last metric, sent only after every batch has
  // landed: Promise.all gives no ordering, so folding it into a batch could
  // close the run before its other events arrived. It used to be sent as an
  // EXTRA event repeating the last value on a new seq, which the server
  // stored as a genuine measurement — every persisted run ended with its
  // final epoch recorded twice.
  const last = metrics[metrics.length - 1];
  if (last) {
    await sidecar.pushEvent(runId, {
      seq: metrics.length - 1,
      epoch: last.epoch,
      canonical_key: last.canonical_key,
      raw_key: last.canonical_key,
      value: last.value,
      finished: true,
    });
  }

  return runId;
}
