/**
 * A quiet terminal in a framework's preamble chooses no parser — mirrors
 * tests/integration/test_live_preamble_pause.py.
 *
 * A quiet terminal settles on what has arrived (the panel calls settle()
 * after 1.5 s). 0.7.40 settled once some parser read a number, and setup
 * lines have numbers: Lightning's "IPU available: False, using: 0 IPU cores"
 * and Ultralytics' "Fast image access (ping: 0.1 ms …" chose the universal
 * parser, and the story gained frames without an epoch, named `using` or
 * `ping`. A pause on YOLO's first epoch did too: its parser reads the row,
 * but its sniff had not seen enough rows to be chosen.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import { StandaloneEngine } from "../../webview/StandaloneEngine";

const REPO = path.resolve(__dirname, "../../../..");

interface Inner {
  _activeParsers: { name: string }[] | null;
}

function story(engine: StandaloneEngine): [number | null, string, number, string][] {
  return engine
    .snapshot()
    .map((f) => [f.epoch, f.primaryMetric, f.primaryMetricValue, f.grade]);
}

function chosen(engine: StandaloneEngine): string[] | null {
  return (engine as unknown as Inner)._activeParsers?.map((p) => p.name) ?? null;
}

const CASES: [string, string, number, string][] = [
  ["lightning setup", "demo/pytorch_lightning.log", 3, "pytorch_lightning"],
  ["yolo setup", "tests/fixtures/logs/yolo_real_ultralytics.log", 35, "ultralytics_yolo"],
  ["yolo first epoch", "tests/fixtures/logs/yolo_real_ultralytics.log", 49, "ultralytics_yolo"],
];

suite("A quiet terminal in a preamble chooses no parser", () => {
  for (const [name, rel, pauseAfter, parser] of CASES) {
    test(`${name}: the story told across the pause is the story without it`, () => {
      const lines = fs.readFileSync(path.join(REPO, rel), "utf-8").split("\n");
      const head = lines.slice(0, pauseAfter).join("\n") + "\n";
      const rest = lines.slice(pauseAfter).join("\n");

      const unpaused = new StandaloneEngine(undefined, "en", null);
      unpaused.feed(head + rest);
      unpaused.settle();
      const expected = story(unpaused);
      assert.ok(expected.length > 0 && expected.every(([epoch]) => epoch !== null));

      const paused = new StandaloneEngine(undefined, "en", null);
      paused.feed(head);
      assert.deepStrictEqual(paused.settle(), [], "told something on the preamble");
      assert.strictEqual(chosen(paused), null, "chose a parser on the preamble");
      paused.feed(rest);
      paused.settle();

      assert.deepStrictEqual(chosen(paused), [parser]);
      assert.deepStrictEqual(story(paused), expected);
    });
  }

  test("a loop with its own metric names is still settled on the first pause", () => {
    const engine = new StandaloneEngine(undefined, "en", null);
    let log = "";
    for (let e = 1; e <= 4; e++) log += `epoch=${e} widget_score=${(0.5 + e / 10).toFixed(2)}\n`;
    engine.feed(log);
    engine.settle();
    assert.deepStrictEqual(chosen(engine), ["universal"]);
    assert.deepStrictEqual(
      engine.snapshot().map((f) => f.epoch),
      [1, 2, 3, 4],
    );
  });
});
