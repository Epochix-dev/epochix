/**
 * The extension grades, reads direction and places phases exactly as Python.
 *
 * src/test/fixtures/grading.golden.json is written by
 * scripts/gen_ts_engine_tables.py from the Python functions themselves —
 * compute_grade across every band edge of every task and metric,
 * grade_by_trajectory, metric_lower_better for every canonical and raw name,
 * relative_improvement, compute_phase and grade_note — and
 * tests/unit/test_ts_engine_tables_sync.py fails if it is stale. Replaying it
 * here means the hand-ported logic cannot drift from Python unseen, as it had:
 * no first-reading phase baseline, an unclamped improvement ratio, a made-up
 * 0.05 of progress, and direction pins Python did not have.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import {
  computeGrade,
  gradeByTrajectory,
  gradeNote,
  metricLowerBetter,
  type Grade,
  type TaskType,
} from "../../story/grader";
import { computePhase, relativeImprovement } from "../../story/phases";

interface Golden {
  compute_grade: [TaskType, number, string | null, Grade][];
  grade_by_trajectory: [number, number, boolean, Grade][];
  metric_lower_better: Record<string, boolean | null>;
  relative_improvement: [number, number, boolean, number | null][];
  compute_phase: [number | null, number, number, boolean, string][];
  grade_note: [Grade, number, boolean, boolean, string | null][];
}

function golden(): Golden {
  const ext = vscode.extensions.getExtension("epochix.epochix");
  assert.ok(ext, "extension epochix.epochix not found");
  const file = path.join(ext.extensionPath, "src", "test", "fixtures", "grading.golden.json");
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Golden;
}

/** Mismatches as readable lines, so one run shows every drift at once. */
function check<T>(cases: T[], name: string, compare: (c: T) => string | null): void {
  assert.ok(cases.length > 50, `${name}: the golden has almost no cases`);
  const wrong = cases.map(compare).filter((w): w is string => w !== null);
  assert.deepStrictEqual(wrong.slice(0, 20), [], `${name}: ${wrong.length} of ${cases.length} differ`);
}

suite("Grading matches the Python engine", () => {
  const g = golden();

  test("compute_grade, across every band edge", () => {
    check(g.compute_grade, "compute_grade", ([task, value, metric, want]) => {
      const got = computeGrade(task, value, metric);
      return got === want ? null : `${task} ${value} ${metric}: ${got} != ${want}`;
    });
  });

  test("grade_by_trajectory", () => {
    check(g.grade_by_trajectory, "grade_by_trajectory", ([baseline, current, lower, want]) => {
      const got = gradeByTrajectory(baseline, current, lower);
      return got === want ? null : `${baseline} -> ${current} (${lower}): ${got} != ${want}`;
    });
  });

  test("metric_lower_better, for every canonical and raw name", () => {
    const cases = Object.entries(g.metric_lower_better);
    check(cases, "metric_lower_better", ([name, want]) => {
      const got = metricLowerBetter(name) ?? null;
      return got === want ? null : `${name}: ${got} != ${want}`;
    });
  });

  test("relative_improvement", () => {
    check(g.relative_improvement, "relative_improvement", ([value, baseline, lower, want]) => {
      const got = relativeImprovement(value, baseline, lower);
      return got === want ? null : `${value} from ${baseline} (${lower}): ${got} != ${want}`;
    });
  });

  test("compute_phase", () => {
    check(g.compute_phase, "compute_phase", ([progress, value, baseline, lower, want]) => {
      const got = computePhase(progress, value, baseline, lower);
      return got === want ? null : `p=${progress} ${value} from ${baseline} (${lower}): ${got} != ${want}`;
    });
  });

  test("grade_note", () => {
    check(g.grade_note, "grade_note", ([grade, readings, hasEpoch, newBest, want]) => {
      const got = gradeNote(grade, readings, { hasEpoch, newBest });
      return got === want ? null : `${grade} ${readings} ${hasEpoch} ${newBest}: ${got} != ${want}`;
    });
  });
});
