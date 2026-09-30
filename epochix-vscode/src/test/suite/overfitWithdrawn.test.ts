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
