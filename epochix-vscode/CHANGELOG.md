# Changelog — Epochix (VS Code Extension)

Notable changes to the extension. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The extension version tracks the Python package; bug fixes in the shared
frontend ship to both at once.

**This file stopped being updated after 0.2.0.** Every release from 0.2.1 to
0.7.15 is recorded in the
[project changelog](https://github.com/epochix-dev/epochix/blob/main/CHANGELOG.md),
which covers the extension too; entries here resume with 0.7.16.

---

## [0.7.25] — 2026-10-01

### Changed

- **Story sentences say only what the run's numbers support**, in English,
  French and Farsi. They used to add claims no log shows — "near-expert
  performance", "ready to ship", "the model handles glasses, makeup, and
  partial occlusion", and "the model sees faces but not people" on a
  fingerprint run. A sentence now states the reading, names the phase, and
  says how far the phase's own threshold puts the run from where it started.
  A change in a percentage metric is told in points ("+5.5 points").

### Fixed

- **The diagnostics card and the plain-English panel gave one run opposite
  verdicts** on its train/validation gap ("overfitting" against "a small gap,
  so it learned the real patterns"). Both now read the gap the same way, from
  its size and from whether validation is still improving, and say
  "overfitting" only when validation has passed its best.
- The student analogy names training and validation data; a model drawn as
  blocks is counted in modules, not layers.

## [0.7.24] — 2026-09-30

### Fixed

- **A warm-up blip in validation loss was reported as overfitting for the
  rest of the run.** The warning is withdrawn when validation loss reaches a
  new best, and fires again if the run really overfits later.
- **A `print(model)` architecture reads as the model is built** — a ResNet-18
  is a stem, eight residual blocks and a classifier, not its stages and their
  blocks mixed together — and layers are labelled from the Python engine's
  table, generated rather than hand-copied.
- A warning message from a log can no longer name an object key in the
  dashboard (a CodeQL finding on the release's pull request).
- The warning strip no longer lists planned learning-rate drops; the grade
  card no longer repeats the grade; the learning-curve legend no longer sits
  on the curve.

## [0.7.23] — 2026-09-30

No change to the extension itself; released in step with the Python package,
whose release fixes rough edges in its command line.

## [0.7.22] — 2026-09-29

No change to the extension itself; released in step with the Python package,
whose release fixes garbled piped output on Windows.

## [0.7.21] — 2026-09-29

No change to the extension itself; released in step with the Python package,
whose release withdraws a stale Claude artifact and fixes links and notes
around the project.

## [0.7.20] — 2026-09-29

### Fixed

- **The panel no longer contacts Google.** Its fonts were fetched from
  fonts.googleapis.com every time a dashboard opened; they ship inside the
  extension now, and the panel's Content-Security-Policy admits fonts only as
  inline data.

## [0.7.19] — 2026-09-29

### Fixed

- The skill radar cut axis names to ten characters ("Val Accura"); they are
  wrapped whole and fit the panel. The parameter share reads "<1%" for a real
  layer rather than "0%".
- The bundled LICENSE is the verbatim Apache 2.0 text; it was a paraphrase.

## [0.7.18] — 2026-09-28

### Fixed

- **A one-epoch run, or a fit-once result, ended its story in the wrong
  phase.** The extension's grading and phase logic was a hand copy of the
  Python engine's and had drifted; it now grades from tables generated from
  the Python engine and replays 2,800 of its answers in its tests, so the
  extension and the Python package tell every run the same way.

## [0.7.17] — 2026-09-28

### Added

- **The parameter search on the dashboard.** A GridSearchCV run shows every
  setting it tried — mean, spread, range and folds, with the one that was
  charted marked — in a *Parameter search* panel, and a plain
  cross-validation shows its folds. Works without the Python package: the
  extension's engine now hands on the folds it collects.
- **The comparison as a PDF**, beside the Markdown download in the comparison
  view: the explanation, the runs' curves overlaid, and each run's numbers.

## [0.7.16] — 2026-09-25

### Added

- **An empty dashboard explains itself.** A panel opened with no log and no
  terminal read "Waiting for training data…" forever. It now says nothing is
  loaded and offers *Try the demo*, *Open a log file* and *Watch the active
  terminal* as buttons. A log with no metrics says so instead of waiting.
- **A run that went wrong is told what to do next** — past its peak, stalled,
  diverged, overfitting, plateaued — in English, Farsi and French.
- **A grade says when it is provisional**: fewer than five readings, or a
  metric still setting new bests. Shown under the grade.
- **The comparison view can download a written comparison** (Markdown) beside
  the race GIF, and its labels are translated.

### Fixed

- Frames' `confidence` carried the parser's certainty about a line; it is the
  run's advancement, as in the Python engine.

## [0.2.0] — 2026-05-26

### Added

- **Reproducible webview build** — new `npm run build:webview` in the shared
  frontend emits a single flat `main.js` + `main.css` with all dynamic imports
  inlined (Chart.js bundled in) so the strict webview CSP can admit it. The
  build runs automatically during `vsce package` via `vscode:prepublish`.
- **Webview loader reads the built `index.html`** instead of stamping out a
  bare `<div id=app>` shell, so the full app markup (sidebar, panels,
  sections) is preserved.
- **VS Code postMessage bridge** in the shared frontend — gated on
  `window.__EPOCHIX_VSCODE__`. Standalone mode now receives `init` / `frame` /
  `milestone` / `warning` / `complete` / `themeChange` events from the
  extension's StoryEngine and renders the core story.
- **LICENSE** file copied into the extension directory so the packaged
  `.vsix` carries a license alongside the code.

### Changed

- `.vscodeignore` excludes `**/*.map` (was just `*.map`) and `*.vsix` so the
  packaged extension is leaner.
- `vsce package` is now hermetic — no stale source maps, no extra files.

### Inherits all 0.2.0 dashboard improvements

The webview renders the shared epochix dashboard, so every fix in the
Python package's 0.2.0 release reaches extension users immediately:
secure-by-default CORS / write-auth / docs gating, ANSI-stripping parser,
detection-aware skill radar, live architecture detection during streaming,
PhD-level engineer panel (LR chart, multi-loss decomposition, best-epoch
markers), `epochix demo` onboarding, real-YOLO end-to-end verification.

See the Python package CHANGELOG for full details.

---

## [0.1.0] — 2026-05-22

First public release.

### Added

- Webview dashboard panel — opens with `Ctrl+Alt+M` / `Cmd+Alt+M`
- Sidecar mode — auto-discovers the Python `epochix` package and
  streams metrics from the local server
- Standalone mode — built-in TypeScript engine parses logs in-process
- Open Log File command (right-click `.log` files)
- Watch Active Terminal command — streams a live training session
- Compare Runs view
- Status-bar grade + phase indicator
- Tree-view of stored runs in the Explorer sidebar
