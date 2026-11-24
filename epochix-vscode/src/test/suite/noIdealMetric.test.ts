/**
 * A PSNR or inception-score log, from its text to its frames — mirrors
 * tests/integration/test_no_ideal_metric_story.py, with the same lines and
 * the same phases.
 *
 * Every higher-is-better metric was read as a share of the way to 1.0. These
 * start above 1, so a rising run was placed in Awakening on every frame and
 * told "No meaningful progress yet". Neither has an ideal, so its improvement
 * is measured from the first reading, as the improvement grade measures it.
 */
import * as assert from "assert";

import type { Phase } from "../../story/phases";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const PSNR = [20.0, 21.5, 23.0, 24.4, 25.7, 26.9, 28.0, 29.0, 29.9, 30.7, 31.4, 32.0];
const IS = [2.0, 2.6, 3.3, 4.0, 4.7, 5.4, 6.0, 6.6, 7.2, 7.8, 8.4, 9.0];

const A: Phase = "awakening";
const L: Phase = "learning";
const U: Phase = "understanding";
const M: Phase = "mastering";
const P: Phase = "polishing";

// [name in the log, readings, whether the line states the run's length,
//  the story's metric, the phase of each frame, the last letter]
const CASES: [string, number[], boolean, string, Phase[], string][] = [
  ["psnr", PSNR, true, "PSNR", [A, L, L, L, L, L, U, U, U, U, U, U], "A"],
  ["psnr", PSNR, false, "PSNR", [A, A, L, L, L, L, U, U, U, U, U, U], "A"],
  ["inception_score", IS, true, "is_score", [A, L, L, L, U, U, U, U, M, M, M, P], "A+"],
  ["inception_score", IS, false, "is_score", [A, L, U, P, P, P, P, P, P, P, P, P], "A+"],
];

function lines(name: string, values: number[], withTotal: boolean): string[] {
  return values.map(
    (v, i) => `${withTotal ? `Epoch ${i + 1}/12 ` : `Epoch ${i + 1}: `}${name}=${v.toFixed(1)}`,
  );
}

suite("A score with no ideal moves through the phases", () => {
  for (const [name, values, withTotal, metric, phases, grade] of CASES) {
    test(`${name}, ${withTotal ? "with" : "without"} the run's length`, () => {
      const engine = new StandaloneEngine();
      engine.feed(lines(name, values, withTotal).join("\n") + "\n");
      engine.flush();
      const frames = engine.snapshot();
      assert.deepStrictEqual(frames.map((f) => f.primaryMetric), Array(values.length).fill(metric));
      assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), values);
      assert.deepStrictEqual(frames.map((f) => f.phase), phases);
      assert.strictEqual(frames[frames.length - 1].grade, grade);
      assert.strictEqual(frames[frames.length - 1].gradeBasis, "improvement");
      for (const frame of frames) {
        assert.ok(!/progress|barely moved|where it started/.test(frame.narrative), frame.narrative);
      }
      if (!withTotal) {
        // No clock: the progress is the rise over the first reading, to 1.
        for (const frame of frames) {
          const want = Math.min(1, (frame.primaryMetricValue - values[0]) / values[0]);
          assert.ok(Math.abs(frame.progress - want) < 1e-9, `${frame.progress} != ${want}`);
        }
      }
    });
  }
});
