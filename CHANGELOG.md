# Changelog

All notable changes to **epochix** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.9] — 2026-07-13

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
