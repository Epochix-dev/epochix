/**
 * A run that reports F1 has a task, and a story — mirrors
 * tests/integration/test_f1_tells_a_story.py.
 *
 * F1 was no task signal, so a log reporting it fell to the `custom` task,
 * whose story is told on a loss: a log with only F1 produced no frame at all,
 * and one with F1 and a loss was told on the loss.
 */
import * as assert from "assert";

import { computeGrade } from "../../story/grader";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const F1 = [0.4, 0.55, 0.7, 0.8, 0.84];

function told(lines: string[]): StandaloneEngine {
  const engine = new StandaloneEngine();
  engine.feed(lines.join("\n") + "\n");
  engine.flush();
  return engine;
}

suite("A run that reports F1 has a story", () => {
  test("a log with only F1 is told", () => {
    const engine = told(F1.map((v, i) => `Epoch ${i + 1}/5 val_f1=${v}`));
    const frames = engine.snapshot();
    assert.deepStrictEqual(frames.map((f) => f.primaryMetric), Array(5).fill("val_f1"));
    assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), F1);
    assert.strictEqual(frames[4].taskType, "classification");
    // Graded where it stands, on accuracy's bands, every frame.
    for (const frame of frames) {
      assert.strictEqual(frame.grade, computeGrade("classification", frame.primaryMetricValue));
      assert.strictEqual(frame.gradeBasis, "thresholds");
    }
  });

  test("F1 beside a loss is the story, not the loss", () => {
    const engine = told(
      F1.map((v, i) => {
        const e = i + 1;
        return `Epoch ${e}/5 train_loss=${(1 / e).toFixed(3)} val_loss=${(1.2 / e).toFixed(3)} val_f1=${v}`;
      }),
    );
    const frames = engine.snapshot();
    assert.strictEqual(frames.length, 5);
    assert.deepStrictEqual([...new Set(frames.map((f) => f.primaryMetric))], ["val_f1"]);
  });

  test("accuracy beside it still tells the story", () => {
    const engine = told(
      F1.map((v, i) => `Epoch ${i + 1}/5 val_accuracy=${(v + 0.05).toFixed(3)} val_f1=${v}`),
    );
    assert.deepStrictEqual(
      [...new Set(engine.snapshot().map((f) => f.primaryMetric))],
      ["val_accuracy"],
    );
  });

  test("a more specific metric beside it still decides the task", () => {
    const engine = told(
      F1.map((v, i) => `Epoch ${i + 1}/5 mAP50=${(v - 0.1).toFixed(3)} f1=${v}`),
    );
    const frames = engine.snapshot();
    assert.ok(frames.length > 0, "no frame was told");
    assert.strictEqual(frames[frames.length - 1].taskType, "detection");
  });
});
