/**
 * The extension reads a `print(model)` dump the way Python does.
 *
 * architecture.golden.json is written by scripts/gen_ts_engine_tables.py from
 * Python's own parse of every corpus log that prints its model, plus a few
 * shapes the corpus lacks. The extension's parser had drifted: it listed a
 * ResNet-18's stages *and* the blocks inside them, and labelled layers from a
 * hand-kept subset of Python's table.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import { parseArchitecture } from "../../story/architecture";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const REPO = path.resolve(__dirname, "../../../..");
const GOLDEN = JSON.parse(
  fs.readFileSync(path.join(REPO, "epochix-vscode", "src", "test", "fixtures", "architecture.golden.json"), "utf8"),
) as {
  logs: Record<string, string[][]>;
  samples: Record<string, { lines: string[]; layers: string[][] }>;
};

function rows(lines: string[]): string[][] {
  return parseArchitecture(lines).map((l) => [
    l.name, l.layer_type, l.tech_label, l.plain_label, l.visual_type,
  ]);
}

suite("Architecture golden", () => {
  test("the golden covers a real log and every sample", () => {
    assert.ok(Object.keys(GOLDEN.logs).includes("tests/fixtures/logs/resnet18_cifar10.log"));
    assert.ok(Object.keys(GOLDEN.samples).length >= 3);
  });

  for (const [rel, want] of Object.entries(GOLDEN.logs)) {
    test(rel, () => {
      const text = fs.readFileSync(path.join(REPO, rel), "utf8");
      assert.deepStrictEqual(rows(text.split(/\r?\n/)), want);
    });
  }

  for (const [name, { lines, layers }] of Object.entries(GOLDEN.samples)) {
    test(`sample: ${name}`, () => {
      assert.deepStrictEqual(rows(lines), layers);
    });
  }
});

/**
 * The whole engine, on every corpus log, against the whole Python pipeline.
 *
 * The extension read Keras and `print(model)` only, so a Lightning or
 * Ultralytics run had its model drawn in the browser and nothing in VS Code.
 */
suite("Architecture parity — the extension draws the model Python draws", () => {
  const pipeline = (GOLDEN as unknown as { pipeline: Record<string, string[][]> }).pipeline;

  test("the golden has logs with a model, in more than one format", () => {
    const withModel = Object.entries(pipeline).filter(([, layers]) => layers.length > 0);
    assert.ok(withModel.length >= 5, `only ${withModel.length} logs carry a model`);
    for (const rel of ["demo/seq2seq_attention.log", "demo/yolov8_detection.log"]) {
      assert.ok((pipeline[rel] ?? []).length > 0, `${rel} has no architecture in the golden`);
    }
  });

  for (const [rel, want] of Object.entries(pipeline)) {
    test(rel, () => {
      const engine = new StandaloneEngine();
      engine.feed(fs.readFileSync(path.join(REPO, rel), "utf8"));
      engine.flush();
      const got = engine.architecture().map((l) => [
        l.name, l.layer_type, l.tech_label, l.plain_label, l.visual_type,
      ]);
      assert.deepStrictEqual(got, want);
    });
  }
});
