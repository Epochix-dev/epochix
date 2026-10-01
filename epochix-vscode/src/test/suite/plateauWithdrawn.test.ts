/**
 * The plateau warning describes the last five readings, so it stands only
 * while it is true of them — mirrors TestPlateauWithdrawn in
 * tests/unit/test_warning_detector.py and
 * tests/integration/test_plateau_withdrawn_e2e.py.
 *
 * The recorded Keras demo (demo/keras_image_classifier.log) moved less than 1%
 * over epochs 10-14, climbed again, and flattened over its last five. The
 * warning fired once at epoch 14 and stood for the rest of the run.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import { StandaloneEngine } from "../../webview/StandaloneEngine";

const REPO = path.resolve(__dirname, "../../../..");
const LOG = path.join(REPO, "demo", "keras_image_classifier.log");

function plateauEvents(engine: StandaloneEngine): Array<[number | null, string]> {
  return engine
    .warnings()
    .filter((w) => w.kind.startsWith("plateau"))
    .map((w) => [w.epoch, w.kind]);
}

function replay(values: number[]): Array<[number | null, string]> {
  const engine = new StandaloneEngine();
  values.forEach((v, i) => {
    engine.feed(`Epoch ${i + 1}/${values.length} val_accuracy=${v.toFixed(4)}\n`);
  });
  engine.flush();
  return plateauEvents(engine);
}

suite("A withdrawn plateau warning", () => {
  const FLAT = [0.7, 0.701, 0.702, 0.703, 0.704];

  test("the real Keras demo withdraws its mid-run plateau", () => {
    const text = fs.readFileSync(LOG, "utf8");
    assert.ok(text.length > 0, "the demo log is empty");
    const engine = new StandaloneEngine();
    engine.feed(text);
    engine.flush();
    assert.deepStrictEqual(plateauEvents(engine), [
      [14, "plateau"],
      [15, "plateau_cleared"],
      [19, "plateau"],
    ]);
  });

  test("a metric that moves again withdraws the warning", () => {
    assert.deepStrictEqual(replay([...FLAT, 0.75]), [
      [5, "plateau"],
      [6, "plateau_cleared"],
    ]);
  });

  test("it fires again if the run flattens later", () => {
    assert.deepStrictEqual(replay([...FLAT, 0.75, 0.751, 0.752, 0.753, 0.754]), [
      [5, "plateau"],
      [6, "plateau_cleared"],
      [10, "plateau"],
    ]);
  });

  test("a run that stays flat keeps its one warning", () => {
    const flat = Array.from({ length: 12 }, (_, i) => 0.7 + 0.0001 * (i + 1));
    assert.deepStrictEqual(replay(flat), [[5, "plateau"]]);
  });
});
