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
cd frontend && npm test
cd epochix-vscode && npm test    # launches a real VS Code host
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

## Tests must execute the path

The dominant source of bugs here has been code that shipped, was documented,
and had never once been run. Unit tests covering the pieces did not catch it;
nothing drove the journey. A new code path needs at least one test that
actually executes it end to end — against the real dependency, not a mock.

Where a test can pass by doing nothing (all skipped, an empty fixture), add a
guard that fails instead. And when narrative or output is chosen at random,
assert over every variant rather than one sampled result.
