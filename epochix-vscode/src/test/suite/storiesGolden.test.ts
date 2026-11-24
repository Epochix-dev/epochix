/**
 * Every log in the repository is told by the extension word for word as the
 * Python engine tells it, in every language.
 *
 * Corpus parity (corpusParity.test.ts) compares each log's metrics, grade,
 * phase and milestones, and never the sentence a frame tells. Measured once
 * over the corpus, the two engines told 4,194 of 4,206 frames differently:
 * they picked a sentence's variant from the run id by different hashes, an
 * exact half was rounded down in Python and up here ("73.2%" against
 * "73.3%"), and this engine never raised the learning-rate warning, nor
 * listed two warnings of one frame in Python's order.
 *
 * src/test/fixtures/stories.golden.json is the whole Python pipeline's
 * telling of each log in corpus_truth.json under run ids chosen to reach every
 * variant of every template: each frame's sentence under each id (one, where
 * every id told the same), and every warning. One id reaches one variant of
 * each, and the extension's "+7.8 points" at a run's first reading hid in a
 * variant it never picked. scripts/gen_ts_engine_tables.py writes the golden,
 * and tests/unit/test_ts_engine_tables_sync.py fails until it is current. A
 * sentence changed in one engine and not the other fails here.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { StandaloneEngine } from "../../webview/StandaloneEngine";

const EXT_ID = "epochix.epochix";
const LOCALES = ["en", "fa", "fr"] as const;

type Warning = [string, number | null, string];
type Told = { frames: [number | null, string][]; warnings: Warning[] };

interface Golden {
  run_ids: string[];
  /** A frame's sentence under each run id, or one when every id told the same. */
  logs: Record<
    string,
    Record<(typeof LOCALES)[number], { frames: [number | null, string | string[]][]; warnings: Warning[] }>
  >;
}

function repoRoot(): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  return path.resolve(ext.extensionPath, "..");
}

function read<T>(...parts: string[]): T {
  return JSON.parse(fs.readFileSync(path.join(repoRoot(), ...parts), "utf-8")) as T;
}

function tell(file: string, locale: string, runId: string): Told {
  const engine = new StandaloneEngine(undefined, locale, null, runId);
  // As DashboardPanel.openLog, and as corpusParity: raw text into feed().
  const frames = [...engine.feed(fs.readFileSync(file, "utf-8")), ...engine.flush()];
  engine.finish();
  return {
    frames: frames.map((f) => [f.epoch, f.narrative]),
    warnings: engine.warnings().map((w) => [w.kind, w.epoch, w.message]),
  };
}

suite("Stories golden — the extension tells every log as Python does", () => {
  const golden = read<Golden>("epochix-vscode", "src", "test", "fixtures", "stories.golden.json");
  const truth = read<Record<string, { path: string }>>("tests", "fixtures", "corpus_truth.json");

  test("the golden covers the whole corpus, in every variant", () => {
    assert.deepStrictEqual(Object.keys(golden.logs).sort(), Object.keys(truth).sort());
    assert.ok(golden.run_ids.length >= 4, `told under ${golden.run_ids.length} run ids`);
    let frames = 0;
    let warnings = 0;
    for (const told of Object.values(golden.logs)) {
      assert.deepStrictEqual(Object.keys(told).sort(), [...LOCALES]);
      for (const locale of LOCALES) {
        frames += told[locale].frames.length;
        warnings += told[locale].warnings.length;
      }
    }
    // Guards: a golden emptied by a broken generator would pass every log.
    assert.ok(frames > 3000, `only ${frames} frames in the golden`);
    assert.ok(warnings > 100, `only ${warnings} warnings in the golden`);
  });

  for (const name of Object.keys(golden.logs).sort()) {
    for (const locale of LOCALES) {
      test(`${name} (${locale})`, () => {
        const want = golden.logs[name][locale];
        golden.run_ids.forEach((runId, n) => {
          const got = tell(path.join(repoRoot(), truth[name].path), locale, runId);
          assert.strictEqual(got.frames.length, want.frames.length, `${runId}: frames`);
          want.frames.forEach(([epoch, said], i) => {
            const sentence = typeof said === "string" ? said : said[n];
            assert.deepStrictEqual(got.frames[i], [epoch, sentence], `${runId}: frame ${i}`);
          });
          assert.deepStrictEqual(got.warnings, want.warnings, `${runId}: warnings`);
        });
      });
    }
  }
});
