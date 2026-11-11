/**
 * Runs that count steps, through the extension's own engine.
 *
 * Python: tests/integration/test_step_counted_runs.py. The three recordings
 * are held to corpus_truth.json by corpusParity.test.ts; this pins what that
 * cannot — which reading sits at which step, and that a bar still being drawn
 * is read as it arrives.
 *
 * A LoRA trainer draws ONE tqdm bar for the whole run and ends no line until
 * the training does. An engine that reads complete lines shows such a run
 * nothing for hours (AGENTS.md: streaming has no end).
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { stepBarRedraws } from "../../parsers/stepBar";
import { StandaloneEngine } from "../../webview/StandaloneEngine";
import type { StoryFrameMsg } from "../../webview/messages";

function fixture(name: string): string {
  const ext = vscode.extensions.getExtension("epochix.epochix");
  assert.ok(ext, "extension epochix.epochix not found");
  const file = path.resolve(ext.extensionPath, "..", "tests", "fixtures", "logs", name);
  const text = fs.readFileSync(file, "utf-8");
  assert.ok(text.length > 2000, `${name} is empty`);
  return text;
}

function told(text: string): { engine: StandaloneEngine; frames: StoryFrameMsg[] } {
  const engine = new StandaloneEngine();
  const frames = [...engine.feed(text), ...engine.flush()];
  return { engine, frames };
}

const range = (from: number, to: number, by = 1): number[] =>
  Array.from({ length: Math.floor((to - from) / by) + 1 }, (_, i) => from + i * by);

suite("Runs that count steps", () => {
  test("nanoGPT is told by its validation loss, step by step", () => {
    const { engine, frames } = told(fixture("nanogpt_real.log"));
    assert.deepStrictEqual([...new Set(frames.map((f) => f.primaryMetric))], ["val_loss"]);
    assert.deepStrictEqual(frames.map((f) => f.epoch), range(0, 2000, 250));
    assert.deepStrictEqual(frames.slice(0, 2).map((f) => f.primaryMetricValue), [4.1649, 2.4447]);
    const metrics = engine.metrics();
    assert.strictEqual(metrics.filter((m) => m.canonical_key === "val_loss").length, 9);
    // Nine estimates on the `step` lines and the loss of every tenth iteration.
    assert.strictEqual(metrics.filter((m) => m.canonical_key === "train_loss").length, 9 + 201);
    // The config file nanoGPT echoes first is not a metric.
    assert.deepStrictEqual([...new Set(metrics.map((m) => m.canonical_key))].sort(), ["train_loss", "val_loss"]);
  });

  test("the ImageNet example is told by its validation accuracy", () => {
    const { engine, frames } = told(fixture("pytorch_imagenet_real.log"));
    const results = frames.filter((f) => f.primaryMetric === "val_accuracy");
    assert.deepStrictEqual(results.map((f) => f.epoch), range(1, 8));
    assert.strictEqual(results[results.length - 1].primaryMetricValue, 0.89);
    // Before the first validation the run has printed a loss and nothing else.
    const before = frames.filter((f) => f.primaryMetric !== "val_accuracy");
    assert.deepStrictEqual([...new Set(before.map((f) => f.primaryMetric))], ["train_loss"]);
    assert.ok(before.every((f) => f.epoch !== null && f.epoch < 1));
    // `Acc@1 10.333` is 10.333%, a fraction here.
    const accuracies = engine.metrics().filter((m) => m.canonical_key.endsWith("accuracy"));
    assert.strictEqual(accuracies.length, 24);
    assert.ok(accuracies.every((m) => m.value >= 0 && m.value <= 1));
  });

  test("a LoRA run is told step by step from the redraws of its one bar", () => {
    const text = fixture("diffusers_lora_real.log");
    // Read in their final state, as every other line is, five readings.
    assert.strictEqual(text.split("\n").filter((l) => l.includes("Steps:")).length, 5);
    const { engine, frames } = told(text);
    assert.deepStrictEqual(frames.map((f) => f.epoch), range(1, 120));
    assert.deepStrictEqual(frames.slice(0, 3).map((f) => f.primaryMetricValue), [0.00856, 0.0162, 0.025]);
    assert.strictEqual(frames[frames.length - 1].primaryMetricValue, 0.00357);
    assert.strictEqual(frames[frames.length - 1].progress, 1);
    assert.strictEqual(engine.metrics().filter((m) => m.canonical_key === "lr").length, 120);
  });

  test("a bar still being drawn is read as it arrives", () => {
    const engine = new StandaloneEngine();
    const bar = (n: number, post: string): string =>
      `\rSteps: ${String(n).padStart(3)}%|##        | ${n}/100 [00:26<00:43,  1.85it/s${post}]`;
    // No newline is ever written: each step moves the counter, then sets the loss.
    for (let n = 1; n <= 100; n++) {
      const previous = n === 1 ? "" : `, loss=${(1 / (n - 1)).toFixed(4)}, lr=0.0001`;
      engine.feed(bar(n, previous));
      engine.feed(bar(n, `, loss=${(1 / n).toFixed(4)}, lr=0.0001`));
    }
    // The terminal goes quiet for a moment, as the panel notices (settle): the
    // parser is chosen on the redraws that have arrived, with no line ended.
    engine.settle();
    const snapshot = engine.snapshot();
    // Only the redraw still in the buffer is unread.
    assert.deepStrictEqual(snapshot.map((f) => f.epoch), range(1, 99));
    assert.strictEqual(snapshot[98].primaryMetricValue, 0.0101);
    // From then on each redraw is read as the next one arrives.
    const next = engine.feed(bar(101, ", loss=0.0100, lr=0.0001"));
    assert.deepStrictEqual(next.map((f) => [f.epoch, f.primaryMetricValue]), [[100, 0.01]]);
    assert.deepStrictEqual(engine.feed(bar(101, ", loss=0.0099, lr=0.0001")), []);
    // The end of the run brings the last one.
    const last = engine.flush();
    assert.deepStrictEqual(last.map((f) => [f.epoch, f.primaryMetricValue]), [[101, 0.0099]]);
  });

  test("a redraw split across two chunks is read once, whole", () => {
    const engine = new StandaloneEngine();
    const redraws: string[] = [];
    for (let n = 1; n <= 150; n++) {
      redraws.push(`\rSteps:   1%|          | ${n}/150 [00:26<00:43,  1.85it/s, loss=${(2 / n).toFixed(4)}, lr=0.0001]`);
    }
    const text = redraws.join("");
    // Cut in the middle of a redraw, wherever that falls.
    for (let at = 0; at < text.length; at += 37) engine.feed(text.slice(at, at + 37));
    engine.flush();
    const frames = engine.snapshot();
    assert.deepStrictEqual(frames.map((f) => f.epoch), range(1, 150));
    assert.strictEqual(frames[149].primaryMetricValue, 0.0133);
  });

  test("only a bar that counts steps is read redraw by redraw", () => {
    const epoch =
      "\rEpoch 1/12:  12%|#1  | 5/43 [00:00<00:00, loss=2.3010]\rEpoch 1/12: 100%|####| 43/43 [00:01<00:00, loss=1.2]";
    assert.strictEqual(stepBarRedraws(epoch), null);
    assert.strictEqual(stepBarRedraws("no carriage return"), null);
    const steps = "\rSteps:   1%|  | 1/120 [00:06<12:07, loss=0.5, lr=0.1]\rSteps:   2%|  | 2/120 [00:07<09:00, loss=0.4, lr=0.1]";
    assert.deepStrictEqual(stepBarRedraws(steps), [
      "Steps:   1%|  | 1/120 [00:06<12:07, loss=0.5, lr=0.1]",
      "Steps:   2%|  | 2/120 [00:07<09:00, loss=0.4, lr=0.1]",
    ]);
    // An epoch's bar, fed without its newline, stays in the buffer whole.
    const engine = new StandaloneEngine();
    assert.deepStrictEqual(engine.feed(epoch), []);
  });
});
