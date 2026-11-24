/**
 * pytest's output, which names metrics without measuring any.
 *
 * Its report of a failing test is source code and the values the assertion
 * compared ("    val_loss = 0.42", "E   assert 0.42 < 0.3"), and its test ids
 * are names ("test_model.py::test_learning_rate_schedule_decays PASSED"). A
 * recorded `pytest -v` (tests/fixtures/terminal/pytest.log) scored 0.60 on the
 * terminal detector from those, opened the dashboard, and was told as a run
 * with one reading of `val_loss`, taken from the test's own source.
 *
 * The report opens with a rule naming its section ("===== FAILURES =====", or
 * ERRORS) and the next rule ends it. The universal parser claims every line
 * between (a port of PYTEST_SECTION in parsers/universal.py); the detector
 * does not score them, nor a test id.
 */

/** A section rule: "===== short test summary info =====". Bounded. */
export const PYTEST_SECTION = /^={3,200} (.{1,200}?) ={3,200}$/;
/** The sections that report a failing test. */
export const PYTEST_REPORTS: ReadonlySet<string> = new Set(["FAILURES", "ERRORS"]);

/** A test id: `test_model.py::test_name` or `tests/x.py::Class::test[param]`. */
const TEST_ID = /[\w./\\-]{1,200}\.py::\S{1,200}/g;

/** Whether `line` is a section rule, and if so whether it opens a report. */
export function pytestSection(line: string): boolean | null {
  if (!line.startsWith("===")) return null;
  const m = PYTEST_SECTION.exec(line.trimEnd());
  return m === null ? null : PYTEST_REPORTS.has(m[1]);
}

/** `text` without pytest's failure reports and test ids, for the detector to score. */
export function withoutTestReport(text: string): string {
  if (!text.includes("===") && !text.includes(".py::")) return text;
  const kept: string[] = [];
  let inReport = false;
  for (const line of text.split("\n")) {
    const section = pytestSection(line);
    if (section !== null) inReport = section;
    if (inReport) continue;
    kept.push(line.includes(".py::") ? line.replace(TEST_ID, " ") : line);
  }
  return kept.join("\n");
}
