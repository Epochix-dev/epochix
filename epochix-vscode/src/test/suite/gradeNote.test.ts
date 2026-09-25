/**
 * A letter says when it deserves less weight — mirrors tests/unit/test_grade_note.py.
 *
 * The rule itself is checked here; that both engines reach the same note from
 * the same log is checked over the whole corpus in corpusParity.test.ts.
 */
import * as assert from "assert";

import { FEW_READINGS, gradeNote } from "../../story/grader";
import { StandaloneEngine } from "../../webview/StandaloneEngine";
import type { StoryFrameMsg } from "../../webview/messages";

suite("Grade note", () => {
  test("few readings", () => {
    for (let n = 1; n < FEW_READINGS; n++) {
      assert.strictEqual(gradeNote("A", n, { hasEpoch: true, newBest: true }), "few_readings");
    }
  });

  test("a new best after enough readings is still improving", () => {
    assert.strictEqual(
      gradeNote("B", FEW_READINGS, { hasEpoch: true, newBest: true }), "still_improving");
  });

  test("a settled run, a fit-once result and an I grade have no note", () => {
    assert.strictEqual(gradeNote("B", 200, { hasEpoch: true, newBest: false }), null);
    assert.strictEqual(gradeNote("A", 1, { hasEpoch: false, newBest: true }), null);
    assert.strictEqual(gradeNote("I", 2, { hasEpoch: true, newBest: true }), null);
  });

  test("the engine puts it on its frames, and the run's advancement in confidence", () => {
    const engine = new StandaloneEngine();
    const frames: StoryFrameMsg[] = [];
    for (let e = 1; e <= 8; e++) {
      frames.push(...engine.feed(
        `Epoch ${e}/8 train_loss=${(1 / e).toFixed(4)} val_accuracy=${(0.5 + 0.04 * e).toFixed(4)}\n`));
    }
    frames.push(...engine.flush());
    assert.ok(frames.length >= 5, `too few frames: ${frames.length}`);
    assert.strictEqual(frames[0].gradeNote, "few_readings");
    assert.strictEqual(frames[frames.length - 1].gradeNote, "still_improving");
    // `confidence` carried the parser's certainty about the line; the Python
    // engine has always put the run's advancement there.
    for (const f of frames) assert.strictEqual(f.confidence, f.progress);
  });
});
