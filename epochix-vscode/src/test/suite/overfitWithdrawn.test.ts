/**
 * A warm-up blip is not memorising — mirrors TestOverfitWithdrawn in
 * tests/unit/test_warning_detector.py.
 *
 * A real ResNet-18 on CIFAR-10 (tests/fixtures/logs/resnet18_cifar10.log) rose
 * 0.862 -> 0.867 -> 1.229 in validation loss during its learning-rate warm-up,
 * set a new best at epoch 6 and fell to its lowest at epoch 30. The overfit
 * warning fired at epoch 5 and stood for the rest of the run, telling the
 * reader to "stop at the best validation epoch" — epoch 30.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import { StandaloneEngine } from "../../webview/StandaloneEngine";

const REPO = path.resolve(__dirname, "../../../..");
const LOG = path.join(REPO, "tests", "fixtures", "logs", "resnet18_cifar10.log");

function overfitEvents(engine: StandaloneEngine): Array<[number | null, string]> {
  return engine
    .warnings()
    .filter((w) => w.kind.startsWith("overfit"))
    .map((w) => [w.epoch, w.kind]);
}

suite("A withdrawn overfit warning", () => {
  test("the real ResNet-18 run withdraws its warm-up warning a frame later", () => {
    const text = fs.readFileSync(LOG, "utf8");
    assert.ok(text.length > 0, "the fixture is empty");
    const engine = new StandaloneEngine();
    for (const line of text.split(/\r?\n/)) engine.feed(line + "\n");
    engine.flush();
    assert.deepStrictEqual(overfitEvents(engine), [
      [5, "overfit"],
      [6, "overfit_cleared"],
    ]);
  });

  test("a loss printed after the story's metric counts for its own epoch", () => {
    // Mirrors tests/unit/test_process_line.py: val_accuracy first, val_loss
    // after it. Python fed events one at a time and warned a line late (5).
    const lines: Array<[number, number, number, number]> = [
      [1, 0.6, 0.9, 1.0], [2, 0.7, 0.7, 0.8], [3, 0.72, 0.75, 0.6],
      [4, 0.71, 0.82, 0.45], [5, 0.7, 0.9, 0.35],
    ];
    const engine = new StandaloneEngine();
    for (const [e, acc, vl, tl] of lines) {
      engine.feed(`Epoch ${e}/5 val_accuracy=${acc} val_loss=${vl} train_loss=${tl}\n`);
    }
    engine.flush();
    assert.deepStrictEqual(overfitEvents(engine), [[4, "overfit"]]);
  });

  test("it fires again if the run overfits later", () => {
    const rows: Array<[number, number]> = [
      [1.5462, 1.3929], [1.0401, 0.9918], [0.8426, 0.8622], [0.6934, 0.8667],
      [0.6003, 1.2294], [0.5384, 0.6369], [0.483, 0.6396], [0.4398, 0.568],
      [0.4, 0.6], [0.38, 0.62], [0.36, 0.65],
    ];
    const engine = new StandaloneEngine();
    rows.forEach(([train, val], i) => {
      const e = i + 1;
      engine.feed(`Epoch ${e}/11 train_loss=${train.toFixed(4)} val_loss=${val.toFixed(4)}\n`);
    });
    engine.flush();
    assert.deepStrictEqual(overfitEvents(engine), [
      [5, "overfit"],
      [6, "overfit_cleared"],
      [10, "overfit"],
    ]);
  });
});
