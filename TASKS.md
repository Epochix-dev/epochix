# Epochix / epochix — Master Task List

> Senior-developer view of every task required to ship v0.1 + VS Code extension + Claude artifact.
> Update status: `[ ]` = todo, `[~]` = in progress, `[x]` = done, `[!]` = blocked.
> See `memory/impl_progress.md` for session-by-session status.

---

## Phase 0 — Project Scaffold (Week 1)

### P0.1 Repo & Tooling
- [x] Create directory tree (all directories from §22)
- [x] `pyproject.toml` — hatchling, all deps, entry points, optional groups
- [x] `Makefile` — install, dev, test, lint, typecheck, build, clean
- [x] `.pre-commit-config.yaml` — ruff, black, mypy, trailing-whitespace
- [x] `docker-compose.yml` — server + redis + postgres + ollama stubs
- [x] `.github/workflows/ci.yml` — lint + typecheck + test matrix (3.10/3.11/3.12)
- [ ] `.github/workflows/release.yml` — build wheel + publish to PyPI on tag
- [ ] `.github/workflows/benchmarks.yml` — parser perf on every PR
- [ ] `.gitignore`
- [ ] `LICENSE` (Apache-2.0)
- [ ] `CHANGELOG.md` skeleton
- [ ] `scripts/generate-fake-log.py`
- [ ] `scripts/benchmark-parsers.py`
- [ ] `scripts/update-vendored-frontend.sh`
- [ ] `scripts/python-to-ts-parser.py` (semi-auto TS port helper)

---

## Phase 1 — Core Models (Week 1)

### P1.1 Python Models
- [x] `src/epochix/enums.py` — Phase, Grade, TaskType
- [x] `src/epochix/models.py` — RawLogLine, RawMetric, MetricEvent, StoryFrame, Run, Milestone, Warning, MetaphorCard
- [x] `src/epochix/config.py` — pydantic-settings; EPOCHIX_DB, EPOCHIX_LLM_KEY env vars
- [x] `src/epochix/__init__.py` — public re-exports, __version__
- [ ] `src/epochix/py.typed` — PEP 561 marker
- [ ] Unit tests: `tests/unit/test_models.py`

---

## Phase 2 — Parser Subsystem (Week 1)

### P2.1 Infrastructure
- [x] `src/epochix/parsers/base.py` — BaseParser Protocol, ParserContext dataclass
- [x] `src/epochix/parsers/registry.py` — register_parser decorator, format detector (sniff first 50 lines)

### P2.2 Framework Parsers
- [ ] `src/epochix/parsers/pytorch_lightning.py` — regex: `Epoch \d+/\d+:.*loss=`
- [ ] `src/epochix/parsers/keras_tensorflow.py` — regex: `Epoch \d+/\d+` + progress bar
- [ ] `src/epochix/parsers/huggingface.py` — regex: JSON-like `{'loss': ..., 'epoch': ...}`
- [ ] `src/epochix/parsers/ultralytics_yolo.py` — regex: columns `box cls dfl` + `mAP50`
- [ ] `src/epochix/parsers/fastai.py` — regex: tabular `train_loss valid_loss metric time`
- [ ] `src/epochix/parsers/accelerate.py` — regex: similar to HuggingFace
- [ ] `src/epochix/parsers/universal.py` — three-pattern regex fallback (key=val, key: val, JSON)
- [ ] `src/epochix/parsers/llm_fallback.py` — Ollama/OpenAI batch extraction (opt-in)

### P2.3 Demo Fixtures
- [ ] `demo/pytorch_lightning.log` — realistic 30-epoch run
- [ ] `demo/keras_image_classifier.log`
- [ ] `demo/huggingface_bert.log`
- [ ] `demo/yolov8_detection.log`
- [ ] `demo/gaze_estimation.log`
- [ ] `demo/fingerprint_matching.log`
- [ ] `tests/fixtures/logs/` — 30 files including malformed ones

### P2.4 Tests
- [ ] `tests/unit/test_parsers.py` — ≥95% coverage, one test per fixture
- [ ] Hypothesis fuzz: universal parser never crashes on arbitrary input

---

## Phase 3 — Normalizer (Week 1)

- [ ] `src/epochix/normalizer/canonical_keys.py` — mapping table (val_acc→val_accuracy, etc.)
- [ ] `src/epochix/normalizer/units.py` — unit normalization and inference
- [ ] `src/epochix/normalizer/__init__.py` — normalize(RawMetric) → MetricEvent
- [ ] `tests/unit/test_normalizer.py`

---

## Phase 4 — Story Engine (Week 2)

### P4.1 Core Logic
- [ ] `src/epochix/story_engine/task_classifier.py` — fires once on ≥3 events; decision table from §10.2
- [ ] `src/epochix/story_engine/phases.py` — hybrid progress+metric phase detector (§10.3)
- [ ] `src/epochix/story_engine/grade.py` — task-specific thresholds; reads .epochix.yaml
- [ ] `src/epochix/story_engine/milestones.py` — 8 milestone kinds, fire-at-most-once (§10.6)
- [ ] `src/epochix/story_engine/warnings.py` — overfit / plateau / divergence (§10.7)
- [ ] `src/epochix/story_engine/narrator.py` — deterministic template engine (§10.5)
- [ ] `src/epochix/story_engine/__init__.py` — StoryEngine class, process(MetricEvent) → StoryFrame

### P4.2 Narrative Templates
- [ ] `templates/classification/{awakening,learning,understanding,mastering,polishing}.txt` — 3-5 variants each
- [ ] `templates/detection/` — all 5 phases
- [ ] `templates/regression/` — all 5 phases
- [ ] `templates/biometric/` — all 5 phases (EER context)
- [ ] `templates/gaze/` — all 5 phases (MAE in degrees/cm)
- [ ] `templates/nlp/` — all 5 phases (perplexity context)
- [ ] `templates/generative/` — all 5 phases
- [ ] `templates/classification/fa.txt`, `fr.txt` — i18n variants (Farsi, French)
- [ ] Same i18n coverage for all task types

### P4.3 Grade Thresholds Config
- [ ] Default `.epochix.yaml` with all task thresholds from §10.4
- [ ] Config loader in grade.py

### P4.4 Tests
- [ ] `tests/unit/test_story_engine.py` — ≥90% coverage, deterministic across repeated runs

---

## Phase 5 — Storage Layer (Week 2)

- [ ] `src/epochix/store/sqlite_store.py` — SQLAlchemy 2.0 Core; WAL mode; all 5 tables from §7.7
- [ ] `src/epochix/store/migrations/` — Alembic env + initial migration
- [ ] `src/epochix/store/ring_buffer.py` — deque(maxlen=2048) per run, thread-safe
- [ ] `src/epochix/store/__init__.py` — RunStore façade
- [ ] Benchmark: SQLite write throughput ≥ 10k events/sec (`tests/benchmarks/`)
- [ ] `tests/unit/test_store.py`

---

## Phase 6 — Ingestion Layer (Week 2)

- [ ] `src/epochix/ingester/stdin.py` — asyncio StreamReader; Windows msvcrt fallback (§27.3.8)
- [ ] `src/epochix/ingester/file_tail.py` — async tail with inotify/kqueue/polling fallback
- [ ] `src/epochix/ingester/sdk_receiver.py` — receives push events from LiveReporter
- [ ] `src/epochix/ingester/__init__.py` — Ingester ABC + factory

---

## Phase 7 — FastAPI Server (Week 2)

### P7.1 Application
- [ ] `src/epochix/server/app.py` — FastAPI factory, lifespan context, CORS, static files
- [ ] `src/epochix/server/hub.py` — asyncio broadcast hub; per-run channels; bounded queues (256); milestone never dropped
- [ ] `src/epochix/server/routes_runs.py` — GET /api/runs, GET /api/runs/{id}, DELETE /api/runs/{id}, POST /api/runs/{id}/event
- [ ] `src/epochix/server/routes_snapshot.py` — GET /api/snapshot/{id}, GET /api/metrics/{id}, GET /api/raw/{id}
- [ ] `src/epochix/server/routes_export.py` — GET /api/export/{id}/html, /pdf, /md, /json
- [ ] `src/epochix/server/ws.py` — WS /ws/live/{run_id}?last_seq=N; message envelope v1; heartbeat 15s
- [ ] `src/epochix/server/sse.py` — SSE /sse/live/{run_id}; same envelope
- [ ] `src/epochix/server/auth.py` — basic auth + bearer token for team mode
- [ ] GET /api/health — liveness probe
- [ ] GET /api/version — server version + build hash
- [ ] OpenTelemetry tracing instrumentation (optional, from §17.6)

### P7.2 Reconnect & Backpressure
- [ ] Client replay from ring buffer on ?last_seq=N (§6.3)
- [ ] Exponential backoff reconnect protocol documented in messages
- [ ] Overflow coalescing: drop oldest non-milestone on queue full

### P7.3 Tests
- [ ] `tests/integration/test_api.py` — Schemathesis contract tests, 100% endpoints
- [ ] `tests/integration/test_ws.py` — pytest-asyncio; connect/reconnect/replay/heartbeat
- [ ] `tests/integration/test_export.py`

---

## Phase 8 — CLI (Week 2–3)

- [ ] `src/epochix/cli.py` — Typer app; all commands from §15.1:
  - `epochix <log_file>` (batch)
  - `epochix --live` (stdin)
  - `epochix --live --tail FILE`
  - `epochix --port N`
  - `epochix --task <type>`
  - `epochix --no-llm`
  - `epochix --headless --export html`
  - `epochix compare run1 run2`
  - `epochix prune --older-than 30d`
  - `epochix compact`
  - `epochix list`
  - `epochix open <run_id>`
  - `epochix config show|set <k> <v>`
  - `epochix serve --port N --no-browser`
  - `epochix dump-schema` (for TS port generation)

---

## Phase 9 — Python SDK (Week 3)

- [ ] `src/epochix/sdk/live_reporter.py` — LiveReporter class; context manager; auto-finish on exception
- [ ] `src/epochix/sdk/parse.py` — parse() and parse_string() public functions
- [ ] `src/epochix/sdk/compare.py` — compare() for side-by-side run diff
- [ ] `src/epochix/sdk/visualize.py` — visualize() opens browser; serve() returns URL
- [ ] `src/epochix/sdk/export.py` — export() delegates to exporters/
- [ ] Add `@story` decorator pattern (§27.3.2 Pattern 5)
- [ ] Integration tests for all 5 SDK patterns

---

## Phase 10 — Frontend (Week 3)

### P10.1 Project Setup
- [ ] `frontend/package.json` — Vite 5, Chart.js, D3 v7 (path module), Lucide
- [ ] `frontend/vite.config.js` — single-file build mode, base64 font inlining
- [ ] `frontend/index.html` — shell with correct meta tags + script entries

### P10.2 Core Infrastructure
- [ ] `frontend/src/store.js` — reactive store ~50 LOC (signals pattern from §12.2)
- [ ] `frontend/src/ws-client.js` — WS with exponential backoff (1→2→4→8→max30s), last_seq tracking
- [ ] `frontend/src/sse-client.js` — SSE fallback
- [ ] `frontend/src/main.js` — app shell, panel layout, theme init, WS→SSE→polling tier

### P10.3 Panels
- [ ] `frontend/src/panels/HeroPanel.js` — Brain canvas + grade card + narrative
- [ ] `frontend/src/panels/JourneyPanel.js` — Timeline story cards
- [ ] `frontend/src/panels/SkillsPanel.js` — Radar + liquid fill
- [ ] `frontend/src/panels/TechPanel.js` — Engineer panel (collapsed), Chart.js charts

### P10.4 Visualizations (P0 first)
- [ ] `frontend/src/visualizations/BrainCanvas.js` — Canvas 2D hero (P0); rAF loop; 30fps when backgrounded
- [ ] `frontend/src/visualizations/GradeCard.js` — DOM + CSS animated grade pill (P0)
- [ ] `frontend/src/visualizations/TimelineStory.js` — milestone cards (P0)
- [ ] `frontend/src/visualizations/LearningMeter.js` — SVG liquid fill confidence (P1)
- [ ] `frontend/src/visualizations/ConfidenceBars.js` (P1)
- [ ] `frontend/src/visualizations/SkillRadar.js` — D3 path morph (P1)
- [ ] `frontend/src/visualizations/EpochScrubber.js` — range input; all visuals sync (P1)
- [ ] `frontend/src/visualizations/ImprovementWaterfall.js` — Canvas particles (P2)
- [ ] `frontend/src/visualizations/ParticleField.js` (P2)

### P10.5 Themes & i18n
- [ ] `frontend/src/themes/light.css` — CSS custom properties
- [ ] `frontend/src/themes/dark.css`
- [ ] `frontend/src/i18n/en.json`
- [ ] `frontend/src/i18n/fa.json` (Farsi — RTL)
- [ ] `frontend/src/i18n/fr.json`
- [ ] Embedding API: `?panel=hero&theme=dark` query param support

### P10.6 Tests & Performance
- [ ] Vitest unit tests for store.js and ws-client.js (≥80% coverage)
- [ ] Playwright E2E: smoke + all 6 demo fixtures + viz rendering
- [ ] Lighthouse audit: bundle <200KB gzipped, ≥50fps, <300ms FMP
- [ ] Memory ceiling test: 60-epoch run <80MB browser memory

---

## Phase 11 — Export Pipeline (Week 5)

- [ ] `src/epochix/exporters/html_export.py` — Vite single-file; inline run JSON; base64 fonts; <2MB target
- [ ] `src/epochix/exporters/pdf_export.py` — WeasyPrint; 1 slide/milestone + summary; SVG pre-render
- [ ] `src/epochix/exporters/markdown_export.py` — plain narrative + grade + milestones
- [ ] `src/epochix/exporters/json_export.py` — canonical run JSON; re-importable
- [ ] Playwright visual diff tests for HTML export

---

## Phase 12 — Integrations (Week 6–7)

- [ ] `src/epochix/integrations/lightning.py` — StoryCallback for PyTorch Lightning
- [ ] `src/epochix/integrations/hf.py` — StoryCallback for HuggingFace Trainer
- [ ] `src/epochix/integrations/jupyter.py` — %epochix cell magic; iframe in cell output; works offline in Colab
- [ ] `src/epochix/integrations/tensorboard_import.py` — `epochix import-tensorboard ./runs/`
- [ ] `src/epochix/integrations/wandb_import.py` — `epochix import-wandb <api_key> <run_id>`
- [ ] Test Jupyter magic in Colab
- [ ] `pip install epochix[lightning]` integration test

---

## Phase 13 — Plugin System (Week 9)

- [ ] Finalize all 4 entry-point groups in pyproject.toml (parsers, metaphor_packs, exporters, tasks)
- [ ] Document plugin protocol in docs/plugins.md
- [ ] `src/epochix/parsers/registry.py` — load external plugins at startup via importlib.metadata
- [ ] Metaphor pack YAML loader (epochix.yaml + custom domain packs)
- [ ] Example plugin: `epochix-fairseq` package structure documented
- [ ] Test: external plugin installs and registers cleanly

---

## Phase 14 — VS Code Extension (Week 3–4, parallel)

### P14.1 Project Setup
- [ ] `epochix-vscode/package.json` — manifest with all contributes from §27.1.4
- [ ] `epochix-vscode/tsconfig.json`
- [ ] `epochix-vscode/esbuild.config.mjs`

### P14.2 Extension Core
- [ ] `src/extension.ts` — activate()/deactivate(); ServerManager.maybeStart(); TerminalWatcher
- [ ] `src/config.ts` — vscode.workspace.getConfiguration wrapper
- [ ] `src/statusBar.ts` — grade + phase emoji pill; click opens dashboard

### P14.3 Commands
- [ ] `src/commands/openDashboard.ts`
- [ ] `src/commands/watchTerminal.ts`
- [ ] `src/commands/openLogFile.ts`
- [ ] `src/commands/exportRun.ts`

### P14.4 WebView
- [ ] `src/webview/DashboardPanel.ts` — WebviewPanel manager; retainContextWhenHidden
- [ ] `src/webview/webview.html.ts` — HTML shell loading webview-dist/
- [ ] `src/webview/messages.ts` — typed ExtToWeb / WebToExt protocol from §27.1.6

### P14.5 Terminal Watching
- [ ] `src/terminal/TerminalWatcher.ts` — onDidWriteTerminalData; buffer; feed to parser
- [ ] `src/terminal/TrainingDetector.ts` — heuristic: "does this look like an ML run?"

### P14.6 Sidecar
- [ ] `src/sidecar/ServerManager.ts` — spawn/monitor/kill Python process
- [ ] `src/sidecar/HealthCheck.ts` — poll /api/health until ready (5s timeout)
- [ ] `src/sidecar/PortAllocator.ts` — find free port starting at 7860

### P14.7 TS Parser Ports
- [ ] `src/parsers/base.ts`
- [ ] `src/parsers/pytorchLightning.ts`
- [ ] `src/parsers/keras.ts`
- [ ] `src/parsers/huggingface.ts`
- [ ] `src/parsers/yolo.ts`
- [ ] `src/parsers/universal.ts`

### P14.8 TS Story Engine Ports
- [ ] `src/story/phases.ts`
- [ ] `src/story/grader.ts`
- [ ] `src/story/narrator.ts`
- [ ] `src/story/templates/` — same narrative template text, imported as strings

### P14.9 Distribution
- [ ] CI: `.vsix` build per tag with vendored frontend
- [ ] Publish to VS Code Marketplace (publisher: epochix)
- [ ] Publish to Open VSX (Cursor/Windsurf support)
- [ ] Bundle size check: <5 MB .vsix
- [ ] Test on Cursor, Windsurf

---

## Phase 15 — Claude Artifact (Week 3–4, parallel)

- [ ] `src/epochix/_artifacts/epochix.artifact.jsx` — single-file React
- [ ] Port all parsers to JS (detect + parse interface)
- [ ] Port story engine: phaseFor, gradeFor, narratives, buildFrames
- [ ] BrainCanvas using THREE.js (WebGL in artifact)
- [ ] Skill radar using recharts (not D3, per artifact constraints)
- [ ] Drag-and-drop .log file upload
- [ ] Textarea paste input
- [ ] Epoch scrubber (range input)
- [ ] Engineer charts (recharts LineChart)
- [ ] Blob-based HTML export (<500 KB target)
- [ ] Claude API LLM fallback (fetch /v1/messages from artifact runtime)
- [ ] Marketing banner: "pip install epochix" after dashboard renders
- [ ] `?panel=` embed query param

---

## Phase 16 — GitHub Action (Week 8)

- [ ] `.github/actions/epochix/action.yml` — composite action; run epochix; upload HTML artifact
- [ ] `epochix/comment-action@v1` — post report.md as PR comment
- [ ] Example workflow in README
- [ ] Test on a public repo training workflow

---

## Phase 17 — Docs & Demo (Week 10)

- [ ] `README.md` — 20-second video embed + 3 copy-paste commands + link to docs
- [ ] `docs/index.md` — landing page
- [ ] `docs/quickstart.md` — new user in <60 seconds
- [ ] `docs/parsers.md` — all supported frameworks + regex anchors
- [ ] `docs/plugins.md` — write a custom parser or metaphor pack
- [ ] `docs/deployment.md` — local / team server / Docker / hosted
- [ ] MkDocs-material setup with mkdocstrings
- [ ] `docs.epochix.dev` — deploy via CI on every tag
- [ ] Record 90-second demo video (live training + dashboard side-by-side)
- [ ] `demo/` — all 6 realistic fixture logs

---

## Phase 18 — Performance QA (Week 9–10)

- [ ] `tests/benchmarks/test_parser_throughput.py` — pytest-benchmark; ≥50k lines/sec target
- [ ] `tests/benchmarks/test_store_throughput.py` — ≥10k events/sec target
- [ ] py-spy flame graph CI job in benchmarks.yml
- [ ] Lighthouse CI: bundle <200KB, ≥50fps
- [ ] WebSocket load test: 1000 concurrent connections
- [ ] Memory profiling: <30MB per in-flight run

---

## Phase 19 — v0.1 Release (Week 10)

### P19.1 Quality Gates
- [ ] `pytest -q` green on Linux, macOS, Windows × Python 3.10/3.11/3.12
- [ ] `ruff check` clean
- [ ] `mypy --strict src/epochix` clean
- [ ] `playwright test` green (6 fixture logs E2E)
- [ ] Wheel < 8 MB; exported HTML < 2 MB
- [ ] `pip install epochix` in clean venv → demo log opens dashboard

### P19.2 Packaging & Distribution
- [ ] `release.yml` — build wheel per OS; publish to PyPI on `v*` tag
- [ ] Docker: `ghcr.io/epochix/server:<version>`
- [ ] Docker: `ghcr.io/epochix/full:<version>` (+ Ollama + sample data)
- [ ] SBOM (CycloneDX) generation in release workflow
- [ ] `CHANGELOG.md` — v0.1.0 entry
- [ ] Git tag `v0.1.0`

### P19.3 Launch
- [ ] HN launch post (Show HN)
- [ ] r/MachineLearning post
- [ ] Free hosted demo with public sample runs
- [ ] Tweet/post with 90-second video

---

## Phase 20 — Hosted Version (v0.2+, Week 12+)

- [ ] Postgres migration (asyncpg + SQLAlchemy 2.0 async)
- [ ] Redis pub/sub for multi-worker fan-out
- [ ] OAuth: GitHub + Google
- [ ] Per-run ACL: private / team / public-link / public-listed
- [ ] NGINX/Caddy config with TLS + WS upgrade
- [ ] Docker compose: server + redis + postgres + ollama + nginx
- [ ] Per-run shareable permalinks
- [ ] Opt-in telemetry implementation
- [ ] `epochix config set telemetry true`

---

## Open Items from §26

| # | Status | Decision |
|---|--------|----------|
| 1 | Locked | LLM fallback: Ollama opt-in only; OpenAI as secondary opt-in |
| 2 | Locked | Hosted version: wait until v0.2 |
| 3 | Locked | Plugin system: entry points only for v0.1; versioned API in v0.3 |
| 4 | Deferred | Mobile: read-only single column; defer interactive scrubbing |
| 5 | Locked | i18n: en + fa + fr at launch |
| 6 | Locked | TS frontend rewrite: No; revisit at 5k LOC |
| 7 | Locked | Auth in self-hosted: basic auth + token; OAuth at v0.3 |
| 8 | Locked | Telemetry: OFF, opt-in only, ever |
