/**
 * An AUC is graded on its own scale, not on how far it moved — mirrors
 * tests/unit/test_auc_grade_scale.py.
 *
 * A real LightGBM classifier (tests/fixtures/logs/lightgbm_real_classifier.log)
 * ended at 0.984 validation AUC and was graded C- for a 2.1% gain from its
 * first reading. The bands are generated from Python (grading.generated.ts)
 * and replayed in full by gradingGolden.test.ts; these pin the behaviour the
 * panel shows.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import { computeGrade, gradeByTrajectory, hasAbsoluteScale } from "../../story/grader";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const REPO = path.resolve(__dirname, "../../../..");
const LOG = path.join(REPO, "tests", "fixtures", "logs", "lightgbm_real_classifier.log");

suite("An AUC is graded on its own scale", () => {
  test("the letters start at the published anchors", () => {
    assert.strictEqual(computeGrade("classification", 0.9, "val_AUC"), "A-");
    assert.strictEqual(computeGrade("classification", 0.899, "val_AUC"), "B+");
    assert.strictEqual(computeGrade("classification", 0.8, "val_AUC"), "B-");
    assert.strictEqual(computeGrade("classification", 0.7, "val_AUC"), "C-");
    assert.strictEqual(computeGrade("classification", 0.699, "AUC"), "D");
  });

  test("a coin toss is not a pass", () => {
    assert.strictEqual(computeGrade("classification", 0.51, "val_AUC"), "D");
    assert.strictEqual(computeGrade("classification", 0.5, "val_AUC"), "F");
    assert.strictEqual(computeGrade("classification", 0.31, "val_AUC"), "F");
  });

  test("ROC AUC has a scale; PR AUC, precision and recall do not", () => {
    assert.ok(hasAbsoluteScale("AUC"));
    assert.ok(hasAbsoluteScale("val_AUC"));
    for (const metric of ["PR_AUC", "precision", "recall"]) {
      assert.ok(!hasAbsoluteScale(metric), metric);
    }
  });

  test("F1 shares accuracy's bands", () => {
    // A decision, written down in grade.py: mirrors test_f1_grade_scale.py.
    assert.ok(hasAbsoluteScale("f1"));
    assert.ok(hasAbsoluteScale("val_f1"));
    for (const value of [0.99, 0.91, 0.84, 0.72, 0.61, 0.52, 0.31]) {
      assert.strictEqual(
        computeGrade("classification", value, "val_f1"),
        computeGrade("classification", value),
        String(value),
      );
    }
    // The fault itself: 0.90 -> 0.91 was a C- on improvement.
    assert.strictEqual(gradeByTrajectory(0.9, 0.91, false), "C-");
    assert.strictEqual(computeGrade("classification", 0.91, "val_f1"), "A");
  });

  test("the real LightGBM run is graded where its AUC stands", () => {
    const text = fs.readFileSync(LOG, "utf8");
    assert.ok(text.length > 0, "the fixture is empty");
    const engine = new StandaloneEngine();
    engine.feed(text);
    engine.flush();
    const frames = engine.snapshot();
    assert.strictEqual(frames.length, 60);
    const first = frames[0];
    const last = frames[frames.length - 1];
    assert.strictEqual(last.primaryMetric, "val_AUC");
    assert.strictEqual(last.grade, "A+");
    // What it was graded before: a small move from a high start.
    assert.strictEqual(
      gradeByTrajectory(first.primaryMetricValue, last.primaryMetricValue, false),
      "C-",
    );
    for (const frame of frames) {
      assert.strictEqual(
        frame.grade,
        computeGrade("classification", frame.primaryMetricValue, "val_AUC"),
        `epoch ${frame.epoch}`,
      );
    }
  });
});
