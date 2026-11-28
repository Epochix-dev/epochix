/**
 * Two recorded Stable-Baselines3 runs, through the extension's own engine
 * and through a watched terminal.
 *
 * Python: tests/integration/test_reinforcement_learning.py. The recordings
 * are held to corpus_truth.json by corpusParity.test.ts and told word for
 * word as Python tells them by storiesGolden.test.ts; this pins what those
 * cannot — that each table's reward sits at the counter the table states,
 * read from the log's own text, and that a PPO run in a terminal opens the
 * dashboard while it runs. It used to open nothing: no signal the terminal
 * feed knew was in an SB3 table.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { TerminalFeed } from "../../terminal/TerminalFeed";
import { isTraining } from "../../terminal/TrainingDetector";
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

/** (reward, iterations or null, total_timesteps) of every table, from the text. */
function printed(text: string): Array<[number, number | null, number]> {
  const out: Array<[number, number | null, number]> = [];
  for (const table of text.split("\n-")) {
    const row = (name: string): number | null => {
      const m = new RegExp(String.raw`^\|    ${name} +\| (\S{1,40}) +\|`, "m").exec(table);
      return m === null ? null : Number(m[1]);
    };
    const reward = row("ep_rew_mean");
    const steps = row("total_timesteps");
    if (reward !== null && steps !== null) out.push([reward, row("iterations"), steps]);
  }
  return out;
}

suite("Reinforcement learning — Stable-Baselines3 recordings", () => {
  for (const [name, counter, tables] of [
    ["sb3_ppo_real.log", "iteration", 25],
    ["sb3_dqn_real.log", "step", 105],
  ] as const) {
    test(`${name}: one frame a table, the reward it printed, at its ${counter}`, () => {
      const text = fixture(name);
      const want = printed(text);
      assert.strictEqual(want.length, tables, "the recording is not the one these numbers describe");

      const engine = new StandaloneEngine();
      const frames: StoryFrameMsg[] = [...engine.feed(text), ...engine.flush()];
      assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), want.map(([reward]) => reward));
      assert.deepStrictEqual(
        frames.map((f) => f.epoch),
        want.map(([, iterations, steps]) => (counter === "iteration" ? iterations : steps)),
      );
      assert.deepStrictEqual(new Set(frames.map((f) => f.counter)), new Set([counter]));
      assert.deepStrictEqual(new Set(frames.map((f) => f.primaryMetric)), new Set(["ep_rew_mean"]));
      assert.deepStrictEqual(new Set(frames.map((f) => f.taskType)), new Set(["reinforcement"]));
      assert.strictEqual(frames[frames.length - 1].gradeBasis, "improvement");
    });
  }

  test("a PPO run in a terminal opens the dashboard at its first table", () => {
    const text = fixture("sb3_ppo_real.log");
    const firstTable = text.indexOf("ep_rew_mean");
    assert.ok(isTraining(text.slice(0, text.indexOf("\n-", firstTable) + 2)), "the first table is not training");
    assert.ok(!isTraining(text.slice(0, firstTable)), "the preamble alone looked like training");

    const feed = new TerminalFeed();
    const engine = new StandaloneEngine();
    const frames: StoryFrameMsg[] = [];
    let opened: number | null = null;
    // Terminals do not respect line endings: chunks that cut rows in two.
    for (let at = 0; at < text.length; at += 997) {
      const feedable = feed.push(text.slice(at, at + 997));
      if (feedable === null) continue;
      opened ??= at;
      frames.push(...engine.feed(feedable));
    }
    frames.push(...engine.flush());
    assert.ok(feed.detected, "the dashboard never opened");
    assert.ok(opened !== null && opened <= firstTable, `opened at ${opened}`);
    assert.strictEqual(frames.length, 25);
  });
});
