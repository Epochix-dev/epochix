/**
 * The extension reads a `.epochix.yaml` as the Python loader does.
 *
 * gradeConfig.golden.json is what config_loader.parse_grade_config makes of a
 * set of files — ones that work, ones with a mistake the author can fix, and
 * ones that cannot be read — with the bands it then applies to a list of
 * (task, metric) pairs and the letters those bands give. Written by
 * scripts/gen_ts_engine_tables.py; replayed here against story/gradeConfig.ts.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import {
  bandsFor,
  bandsLowerBetter,
  gradeWithBands,
  parseGradeConfig,
  type Bands,
} from "../../story/gradeConfig";

type JsonBands = Record<string, number | string>;

interface Query {
  task: string;
  metric: string;
  bands: JsonBands | null;
  lower_better: boolean | null;
  grades: Array<[number, boolean, string]>;
}

interface Case {
  yaml: string;
  error: string | null;
  config: {
    grade_thresholds: Record<string, JsonBands>;
    metric_thresholds: Record<string, JsonBands>;
    lower_better: Record<string, boolean>;
    problems: string[];
  } | null;
  queries?: Query[];
}

const GOLDEN = path.resolve(__dirname, "../../../src/test/fixtures/gradeConfig.golden.json");

function golden(): Record<string, Case> {
  return JSON.parse(fs.readFileSync(GOLDEN, "utf8")) as Record<string, Case>;
}

/** JSON has no infinity; the generator writes "inf" and "-inf". */
function decode(bands: JsonBands): Bands {
  const out: Bands = {};
  for (const [label, value] of Object.entries(bands)) {
    out[label] = value === "inf" ? Infinity : value === "-inf" ? -Infinity : (value as number);
  }
  return out;
}

function decodeAll(entries: Record<string, JsonBands>): Record<string, Bands> {
  return Object.fromEntries(Object.entries(entries).map(([k, v]) => [k, decode(v)]));
}

suite("A .epochix.yaml is read as the Python loader reads it", () => {
  const cases = golden();

  test("the golden covers what works, what is wrong, and what cannot be read", () => {
    const all = Object.values(cases);
    assert.ok(all.length >= 20, "gradeConfig.golden.json lost its cases");
    assert.ok(all.some((c) => c.error !== null), "no unreadable file in the golden");
    assert.ok(all.some((c) => (c.config?.problems.length ?? 0) > 0), "no file with a problem");
    assert.ok(all.some((c) => c.config === null && c.error === null), "no file that sets nothing");
    const graded = all.flatMap((c) => c.queries ?? []).filter((q) => q.grades.length > 0);
    assert.ok(graded.length >= 10, "too few graded queries to mean anything");
  });

  for (const name of Object.keys(cases).sort()) {
    test(name, () => {
      const want = cases[name];
      const { config, error } = parseGradeConfig(want.yaml);
      assert.strictEqual(error, want.error, "error");
      if (want.config === null) {
        assert.strictEqual(config, null, "a config where Python has none");
        return;
      }
      assert.ok(config !== null, "no config where Python has one");
      assert.deepStrictEqual(config.gradeThresholds, decodeAll(want.config.grade_thresholds));
      assert.deepStrictEqual(config.metricThresholds, decodeAll(want.config.metric_thresholds));
      assert.deepStrictEqual(config.lowerBetter, want.config.lower_better);
      assert.deepStrictEqual(config.problems, want.config.problems);

      for (const query of want.queries ?? []) {
        const where = `${query.task} / ${query.metric}`;
        const bands = bandsFor(config, query.task, query.metric);
        assert.deepStrictEqual(bands, query.bands === null ? null : decode(query.bands), where);
        if (bands === null) continue;
        assert.strictEqual(bandsLowerBetter(bands), query.lower_better, `${where}: direction`);
        for (const [value, lower, grade] of query.grades) {
          assert.strictEqual(
            gradeWithBands(bands, value, lower),
            grade,
            `${where}: ${value} with lower-better=${lower}`,
          );
        }
      }
    });
  }
});
