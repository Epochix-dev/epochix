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

  const runId = await sidecar.createRun(runName);

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

  return runId;
}
