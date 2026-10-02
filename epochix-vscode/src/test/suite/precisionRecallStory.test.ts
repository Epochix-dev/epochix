/**
 * `precision` and `recall` printed by a training loop are read, and tell a
 * story — mirrors tests/integration/test_precision_recall_story.py.
 *
 * `precision` was dropped as run configuration (Lightning prints
 * `precision=16`), and a log with only precision and recall had no frame.
 */
import * as assert from "assert";

import { makeContext } from "../../parsers/base";
import { KerasParser } from "../../parsers/keras";
import { NEVER_METRICS, VALUE_DECIDES, isSetting } from "../../parsers/neverMetrics";
import { UniversalParser } from "../../parsers/universal";
import { gradeByTrajectory } from "../../story/grader";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const PRECISION = [0.55, 0.6, 0.65, 0.7, 0.75];
const RECALL = [0.45, 0.5, 0.55, 0.6, 0.65];

function told(lines: string[]): StandaloneEngine {
  const engine = new StandaloneEngine();
  engine.feed(lines.join("\n") + "\n");
  engine.flush();
  return engine;
}

function universal(line: string): Array<[string, number]> {
  return new UniversalParser().parseLine(line, makeContext()).map((m) => [m.key, m.value]);
}

suite("precision and recall tell a story", () => {
  test("a fraction is the metric, anything else the numeric precision", () => {
    for (const v of [0, 0.55, 0.87, 1]) assert.ok(!isSetting("precision", v), String(v));
    for (const v of [16, 32, 64, 1.5, -1]) assert.ok(isSetting("precision", v), String(v));
    assert.deepStrictEqual([...VALUE_DECIDES], ["precision"]);
    assert.ok(!NEVER_METRICS.has("precision"));
    assert.ok(!isSetting("recall", 16));
  });

  test("a loop's precision is read; a Lightning setting is not", () => {
    assert.deepStrictEqual(universal("precision=0.55 recall=0.45"), [
      ["precision", 0.55],
      ["recall", 0.45],
    ]);
    assert.deepStrictEqual(universal("precision=16 recall=0.45"), [["recall", 0.45]]);
    assert.deepStrictEqual(universal("precision: 32 recall: 0.45"), [["recall", 0.45]]);
  });

  test("a Keras bar keeps its precision", () => {
    const parser = new KerasParser();
    const ctx = makeContext();
    parser.parseLine("Epoch 1/5", ctx);
    const got = parser
      .parseLine("43/43 - 0s - 5ms/step - loss: 0.42 - precision: 0.8700 - recall: 0.6500", ctx)
      .map((m) => [m.key, m.value]);
    assert.deepStrictEqual(got, [
      ["loss", 0.42],
      ["precision", 0.87],
      ["recall", 0.65],
    ]);
  });

  test("precision and recall alone are told", () => {
    const engine = told(
      PRECISION.map((p, i) => `Epoch ${i + 1}/5 precision=${p} recall=${RECALL[i]}`),
    );
    const frames = engine.snapshot();
    assert.deepStrictEqual(frames.map((f) => f.primaryMetric), Array(5).fill("precision"));
    assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), PRECISION);
    assert.strictEqual(frames[4].taskType, "custom");
    assert.strictEqual(frames[4].grade, gradeByTrajectory(PRECISION[0], PRECISION[4], false));
  });

  test("recall alone is told", () => {
    const frames = told(RECALL.map((r, i) => `Epoch ${i + 1}/5 recall=${r}`)).snapshot();
    assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), RECALL);
  });

  test("a learning rate alone is still no story", () => {
    const lines = [1, 2, 3, 4, 5].map((e) => `Epoch ${e}/5 lr=${(0.01 / e).toFixed(5)}`);
    assert.strictEqual(told(lines).snapshot().length, 0);
  });

  test("a loss still comes first, and a setting does not become the story", () => {
    const lines = [
      "precision=16 batch_size=32",
      ...RECALL.map((r, i) => `Epoch ${i + 1}/5 train_loss=${r} recall=${PRECISION[i]}`),
    ];
    const frames = told(lines).snapshot();
    assert.strictEqual(frames.length, 5);
    assert.deepStrictEqual([...new Set(frames.map((f) => f.primaryMetric))], ["train_loss"]);
  });
});
