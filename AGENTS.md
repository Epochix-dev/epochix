# Working on epochix

Notes for anyone — human or agent — changing this repository. Everything here
is a rule that a past bug turned into one.

## The product principle

**No fabricated data, no placeholders, no invented numbers.** If a value cannot
be derived from the log, show nothing. A zero, a guess, or a smooth synthetic
curve in place of a real measurement is a bug, not a fallback — several
shipped releases were spent removing exactly that. When you cannot compute
something, say so in the UI rather than filling the gap.

## Running the test suite

Use `uv`, exactly as CI does:

```bash
uv run --extra dev pytest tests/unit tests/integration
```

**Do not run a bare `python -m pytest`.** On a machine with epochix also
installed system-wide, that resolves the package from site-packages instead of
`src/`, and your edits appear to do nothing. If a result looks impossible,
check with `python -c "import epochix; print(epochix.__file__)"`.

Never assert on pytest's summary text. `addopts` already contains `-q`, so a
second `-q` makes it `-qq` and the "N passed" line disappears entirely. Count
tests by parsing `--junitxml` output instead.

## The full gate before committing

Run each of these separately — chaining with `&&` means an early failure
silently skips the rest and can leave a stale, misleading result:

```bash
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
uv run --extra dev mypy --strict src/epochix
uv run --extra dev pytest tests/unit tests/integration
```

Both ruff commands matter. `format` alone once let an undefined name ship.

Frontend and extension have their own suites:

```bash
npm --prefix frontend test
npm --prefix epochix-vscode test    # launches a real VS Code host
```

## Traps specific to this repo

- **`.gitignore` has a `*.log` rule.** Any bundled log asset needs an explicit
  negation *and* a test asserting the file exists and is non-empty. A release
  once shipped its headline demo button pointing at a file git had eaten.
- **`frontend/dist/.gitkeep` is load-bearing.** `vite build` empties `dist/`,
  wiping it; `git add -A` then stages the deletion and the docs build breaks on
  fresh checkouts. Restore it before committing, and force-add it (`dist/` is
  ignored).
- **Parsers exist twice.** Python in `src/epochix/parsers/`, TypeScript in
  `epochix-vscode/src/parsers/`. A fix to one must be ported to the other —
  the extension's copies have drifted behind and reintroduced fixed bugs.
- **Unbounded quantifiers are a hang.** Any unanchored regex with `\w+`/`\d+`
  before a delimiter is O(n²) on a long line. Bound them (`\w{1,64}`).
- **Streaming has no end.** The server ingests live runs through
  `StoryEngine.process()`, which never sees an end-of-stream. Do not gate
  emitting a frame on an event that may never arrive.
- **One truth for two engines.** `tests/fixtures/corpus_truth.json` (every
  log in `demo/` and `tests/fixtures/logs/`: task, story metric, frames, last
  value, metric names, where the story's metric starts, the final grade, phase
  and grade note, the cross-validation folds) is asserted by both
  `test_log_corpus_truth.py` and the extension's `corpusParity.test.ts`. A new
  log fails both until it has an entry. Name tables, templates, messages, and
  every grading, direction, phase and pathology threshold are generated from
  Python (`grading.generated.ts`); the few functions that read them are ported
  once and replay `grading.golden.json`, Python's own answers. After changing
  any of it run `make gen-ts-tables` and commit the output;
  `test_ts_engine_tables_sync.py` fails until you do. Do not type a threshold
  into the TypeScript: add it to the Python and the generator.
- **A task and its primary metric are chosen separately.** The task comes from
  the metric *names* in a log, the primary metric from the first *preferred*
  key actually seen, and they routinely disagree — prose that names its metric
  was wrong whenever they did. And a metric whose direction is not pinned
  inherits its task's default silently, so its grade simply comes out
  inverted. Tests assert the direction of every preferred key; keep it so.
- **A story sentence may say only what the numbers support.** The phase
  templates once claimed "near-expert performance", "ready to ship" and "the
  model handles glasses, makeup, and partial occlusion", and told the
  fingerprint demo "the model sees faces but not people". A template gets the
  value, the epoch, the last change and the metric's name — nothing else — so
  it may state those, name the phase, and assert what the engine guarantees
  while a phase story is told (within 1% of the run's best; the phase's
  threshold). `test_story_claims.py` ties the wording to `PHASE_STEPS`: change
  a threshold and the sentences stating it fail. Change all three languages.
- **A demo or a "real" fixture is a recording, made from a neutral folder.**
  Two bundled demos were written by hand in the shape the parsers expected,
  and real PyTorch Lightning output (`Epoch 3:`, not `Epoch 3/10:`) went
  unread for the life of the project; a real Ultralytics run was told as
  segmentation off its settings line. A demo ships with the script that
  produced it (`demo/*_source.py`, `demo/README.md`). The libraries print the
  paths they use, so record from somewhere like `C:\tmp\epochix_demos` or
  `/tmp/epochix_demos`: two fixtures were committed carrying a scratch
  folder's path and a user name. `test_no_machine_paths.py` scans every
  tracked file. Do not edit a capture afterwards; record it again.
- **A parser that recognises a line and reads nothing from it must claim it.**
  Returning `[]` hands the line to the fallback parsers: the Keras parser
  skipped a partial progress bar and the universal parser read it anyway.
  `return claim(ctx)` (Python and TypeScript) says the line is accounted for.
- **A warning states its measurement and stands only while it is true.** The
  plateau warning said the model "has stopped finding new patterns" beside a
  grade card reading "still improving". It now quotes the detector's own
  numbers (`test_warning_detector.py` ties the sentence to the constants), a
  `<kind>_cleared` withdraws a `<kind>` everywhere warnings are shown — the
  store, the report (`standing_warnings`) — and a scrubbed view shows what
  stood at that frame (`warningsInView`), not the run's final warnings.
- **A name can be a setting in one log and a metric in another.** `precision`
  is `16` in a Lightning log and `0.87` in a training loop; listed as
  configuration, the metric was dropped everywhere. A name like that goes in
  `VALUE_DECIDES` (`parsers/_never_metrics.py`), not in the skip list.
- **Grading reads the project's `.epochix.yaml`.** The loader was unit-tested
  and called by nothing for the life of the feature. `active_grade_config()`
  is what the pipeline and the server call; `tests/conftest.py` turns the
  lookup off (`EPOCHIX_GRADE_CONFIG=off`) so a developer's own file cannot
  change a test, and a test of the feature turns it back on. The repository
  root must not hold a live `.epochix.yaml` — the template is
  `.epochix.example.yaml`, inert as shipped. A task's entry applies only to
  the metric in `GOVERNED_METRICS`. The extension reads the file too
  (`story/gradeConfig.ts`, a port of `config_loader.py`): change the loader
  and `gradeConfig.golden.json` — Python's reading of a set of sample files —
  is regenerated and replayed, so add a sample for a new rule.
- **A frame says how its letter was reached.** `StoryFrame.grade_basis` is
  "thresholds", "improvement" or None, set where the grade is computed, in
  both engines, and pinned per log in `corpus_truth.json`. The card under the
  grade reads it. A new way of grading needs a new value and a sentence for it
  in all three languages — not a sentence that is true of most runs.
- **Test what the release builds.** 0.7.5–0.7.10 shipped a blank VS Code panel
  because the extension tests ran against `frontend/dist` (the server build)
  while the release packages `build:webview` output. When a release step
  rebuilds something (`vscode:prepublish`), test the rebuild; before tagging,
  `npx --no-install vsce package` and look inside the `.vsix`.

## Dependabot

Land Dependabot PRs with `make land PR=<n>` (`scripts/land_dependabot.py`),
never the GitHub merge button or `gh pr merge`. A squash merge keeps
`dependabot[bot]` as the commit author, and GitHub builds the Contributors list
from commit authors — 31 such merges once put the bot on it, and `main`'s
history was rewritten on 2026-09-23 to re-author them. The script commits the
same change as the maintainer, closes the PR, and refuses a PR whose CI did not
run on a base containing current `main`: `main` is not branch-protected, so that
check is the only gate a direct push has. Security-update PRs come from
Dependabot too; land them the same way. (Dependabot security updates, secret
scanning and push protection are on since 2026-09-23; the first full-history
secret scan found nothing.)

## Tests must execute the path

The dominant source of bugs here has been code that shipped, was documented,
and had never once been run. Unit tests covering the pieces did not catch it;
nothing drove the journey. A new code path needs at least one test that
actually executes it end to end — against the real dependency, not a mock.

Where a test can pass by doing nothing (all skipped, an empty fixture), add a
guard that fails instead. And when narrative or output is chosen at random,
assert over every variant rather than one sampled result.
