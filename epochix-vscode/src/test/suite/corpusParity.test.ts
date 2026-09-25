/**
 * Every log in the repository, through the extension's own engine, against the
 * same reviewed expectations the Python pipeline is held to
 * (tests/fixtures/corpus_truth.json, tests/integration/test_log_corpus_truth.py).
 *
 * Before this, the two engines disagreed on 25 of 38 logs. The extension
 * narrated metrics named `using` (a Lightning banner), `summary` (a YOLO model
 * summary), `00` (a tqdm timestamp) and `Train` (a dataset size); missed every
 * YOLO validation row behind a preamble; had no fastai parser; and graded
 * Hugging Face runs on training loss because it locked the task after four
 * metrics. One truth file, two engines: a fix to one that is not ported to
 * the other fails here.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { StandaloneEngine } from "../../webview/StandaloneEngine";
import type { StoryFrameMsg } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

interface Expectation {
  path: string;
  task: string;
  metric: string | null;
  frames: number;
  last_value: number | null;
  keys: string[];
  metric_from_epoch: number | null;
}

function repoRoot(): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  return path.resolve(ext.extensionPath, "..");
}

function truth(): Record<string, Expectation> {
  const file = path.join(repoRoot(), "tests", "fixtures", "corpus_truth.json");
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Record<string, Expectation>;
}

function run(file: string): Omit<Expectation, "path"> {
  const engine = new StandaloneEngine();
  // As DashboardPanel.openLog: raw text straight into feed().
  const frames: StoryFrameMsg[] = [...engine.feed(fs.readFileSync(file, "utf-8"))];
  frames.push(...engine.flush());
  const last = frames[frames.length - 1];
  const keys = [...new Set(engine.metrics().map((m) => m.canonical_key))];
  const starts = frames
    .filter((f) => last !== undefined && f.primaryMetric === last.primaryMetric)
    .map((f) => f.epoch)
    .filter((e): e is number => e !== null);
  return {
    task: last ? last.taskType : "custom",
    metric: last ? last.primaryMetric : null,
    frames: frames.length,
    last_value: last ? Math.round(last.primaryMetricValue * 1e4) / 1e4 : null,
    keys: keys.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
    metric_from_epoch: starts.length ? Math.min(...starts) : null,
  };
}

suite("Corpus parity — the extension reads every log as Python does", () => {
  const expected = truth();

  test("the corpus is all there", () => {
    assert.ok(Object.keys(expected).length >= 38, "corpus_truth.json lost its entries");
    for (const [name, want] of Object.entries(expected)) {
      assert.ok(fs.existsSync(path.join(repoRoot(), want.path)), `${name}: ${want.path} missing`);
    }
  });

  for (const name of Object.keys(expected).sort()) {
    test(name, () => {
      const want = expected[name];
      const got = run(path.join(repoRoot(), want.path));
      assert.deepStrictEqual(got.keys, want.keys, "metrics stored");
      assert.deepStrictEqual([got.task, got.metric], [want.task, want.metric], "task / story metric");
      assert.strictEqual(got.frames, want.frames, "frames");
      assert.strictEqual(got.last_value, want.last_value, "last value");
      assert.strictEqual(got.metric_from_epoch, want.metric_from_epoch, "story metric starts at");
    });
  }
});
