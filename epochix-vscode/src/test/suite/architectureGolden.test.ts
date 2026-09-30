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
