/**
 * A number reads in a sentence as Python writes it.
 *
 * `toFixed` rounds an exact half up and Python rounds it to even, so a Keras
 * run's 0.7325 was "73.3%" here and "73.2%" in every other surface.
 * src/test/fixtures/format.golden.json is Python's own `.4f`, `.1f`, `.2e`
 * and `.4g` of exact ties, edges and a spread of magnitudes, written by
 * scripts/gen_ts_engine_tables.py; story/pyFormat.ts must answer the same.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { fixed, general, sci } from "../../story/pyFormat";

type Case = [number | string, string, string, string, string, string];

function value(x: number | string): number {
  if (typeof x === "number") return x;
  return { nan: NaN, inf: Infinity, "-inf": -Infinity, "-0": -0 }[x] ?? NaN;
}

suite("Number formats — the Python engine's, exactly", () => {
  const ext = vscode.extensions.getExtension("epochix.epochix");
  assert.ok(ext, "extension not found");
  const file = path.join(ext.extensionPath, "src", "test", "fixtures", "format.golden.json");
  const golden = JSON.parse(fs.readFileSync(file, "utf-8")) as { cases: Case[] };

  test("the golden holds the exact ties that differed", () => {
    assert.ok(golden.cases.length > 500, `only ${golden.cases.length} cases`);
    const ties = golden.cases.filter(([x]) => x === 73.25 || x === 0.7325 || x === 2.5);
    assert.strictEqual(ties.length, 3);
  });

  test("every case, every format", () => {
    const wrong: string[] = [];
    for (const [raw, f4, f1, pct, e2, g4] of golden.cases) {
      const x = value(raw);
      const got = [fixed(x, 4), fixed(x, 1), fixed(x * 100, 1), sci(x, 2), general(x, 4)];
      const want = [f4, f1, pct, e2, g4];
      got.forEach((g, i) => {
        if (g !== want[i]) wrong.push(`${String(raw)} [${i}]: ${g} != ${want[i]}`);
      });
    }
    assert.deepStrictEqual(wrong, []);
  });
});
