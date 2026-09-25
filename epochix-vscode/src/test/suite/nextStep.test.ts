/**
 * A run that went wrong is told what to do next — mirrors tests/unit/test_next_step.py.
 *
 * The engine described past-peak, stalled and diverged runs and stopped short
 * of the next sentence; whether a reader got advice depended on which variant
 * their run id drew. The step is one fixed sentence per state, appended after
 * every variant in every locale, in both engines.
 */
import * as assert from "assert";

import { StandaloneEngine } from "../../webview/StandaloneEngine";
import {
  message,
  narrateDiverged,
  narratePastPeak,
  narrateStalled,
} from "../../story/narrator";
import { LOCALES, SPECIAL_TEMPLATES } from "../../story/narratives.generated";

const MARKER: Record<string, string> = {
  en: "Next step:",
  fa: "گام بعدی:",
  fr: "Étape suivante :",
};

/** Narrate under enough run ids to draw every variant at least once. */
function everyVariant(narrate: (runId: string) => string, nVariants: number): string[] {
  const seen = new Set<string>();
  for (let i = 0; i < 400; i++) seen.add(narrate(`run-${i}`));
  // Guard: a loop that only ever drew one variant would pass vacuously.
  assert.strictEqual(seen.size, nVariants, `drew ${seen.size} of ${nVariants} variants`);
  return [...seen];
}

function assertEndsWithStep(text: string, step: string, locale: string): void {
  assert.ok(text.endsWith(" " + step), text);
  assert.strictEqual(text.split(MARKER[locale]).length - 1, 1, text);
  assert.ok(!text.includes("{"), text);
}

suite("What to do next", () => {
  test("every locale has a marker", () => {
    assert.deepStrictEqual([...LOCALES].sort(), Object.keys(MARKER).sort());
  });

  for (const locale of LOCALES) {
    test(`every past-peak variant ends with the step (${locale})`, () => {
      const step = message("next_pastpeak", locale, { best_epoch: "7" });
      for (const t of everyVariant(
        (runId) => narratePastPeak({ epoch: 10, value: 0.61, best: 0.79, bestEpoch: 7, runId, locale }),
        SPECIAL_TEMPLATES[locale].pastPeak.length,
      )) assertEndsWithStep(t, step, locale);
    });

    test(`every stalled variant ends with the step (${locale})`, () => {
      const step = message("next_stalled", locale);
      for (const t of everyVariant(
        (runId) => narrateStalled({ epoch: 8, value: 0.116, baseline: 0.101, epochsSeen: 8, runId, locale }),
        SPECIAL_TEMPLATES[locale].stalled.length,
      )) assertEndsWithStep(t, step, locale);
    });

    test(`every diverged variant ends with the step (${locale})`, () => {
      const step = message("next_diverged", locale, { last_epoch: "3" });
      for (const t of everyVariant(
        (runId) => narrateDiverged({ epoch: 4, metric: "val_loss", lastValue: 0.59, lastEpoch: 3, runId, locale }),
        SPECIAL_TEMPLATES[locale].diverged.length,
      )) assertEndsWithStep(t, step, locale);
    });

    test(`an overfit run is told what to do next, end to end (${locale})`, () => {
      // Train loss keeps falling; validation loss bottoms out at epoch 3 and climbs.
      const val = [0.9, 0.7, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85];
      const engine = new StandaloneEngine(undefined, locale);
      const frames = [];
      for (const [i, v] of val.entries()) {
        const e = i + 1;
        frames.push(...engine.feed(
          `Epoch ${e}/8 train_loss=${(0.9 * 0.8 ** e).toFixed(4)} val_loss=${v.toFixed(4)}\n`));
      }
      frames.push(...engine.flush());
      assert.ok(frames.length > 0, "no story at all");
      const last = frames[frames.length - 1].narrative;
      assert.ok(last.endsWith(message("next_pastpeak", locale, { best_epoch: "3" })), last);
      const overfit = engine.warnings().filter((w) => w.kind === "overfit");
      assert.ok(overfit.length > 0, "the overfitting warning did not fire");
      assert.ok(overfit[0].message.includes(MARKER[locale]), overfit[0].message);
    });
  }
});
