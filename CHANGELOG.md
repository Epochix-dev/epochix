# Changelog

All notable changes to **model-story** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

*(nothing yet)*

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
- **Plugin system** — four entry-point groups: `model_story.parsers`, `model_story.metaphor_packs`,
  `model_story.tasks`, `model_story.exporters`; third-party packages can extend any of them

#### Story engine
- **5 training phases** — Awakening → Learning → Understanding → Mastering → Polishing
- **11 letter grades** — A+ through F, with per-task thresholds for 7 task types
- **`.model-story.yaml` config** — override grade thresholds and lower-is-better direction
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

#### CLI (`model-story …`)
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
- **PyTorch Lightning** — `ModelStoryCallback`
- **HuggingFace Transformers** — `ModelStoryCallback` for `Trainer`
- **Jupyter** — `%load_ext model_story`, `%model_story`, `%%model_story` magics
- **TensorBoard** — `import-tensorboard` CLI command
- **Weights & Biases** — `import-wandb` CLI command

#### VS Code extension
- Standalone mode: parses the active terminal log live in the editor
- Sidecar mode: connects to a running `model-story serve` instance
- `Model Story Runs` tree view in the Explorer panel
- `Ctrl+Alt+M` / `Cmd+Alt+M` — open dashboard panel
- Configurable task hint, theme, locale

#### Infrastructure
- **GitHub Actions CI** — lint, typecheck, pytest (3 OS × 3 Python versions), Vitest, E2E, Lighthouse
- **GitHub Actions Release** — wheel (3 OS), PyPI OIDC publish, SBOM (CycloneDX), Docker GHCR
- **GitHub Actions VS Code Release** — `.vsix` build, VS Code Marketplace publish, Open VSX publish
- **Docker image** — `ghcr.io/model-story/server:<version>`, multi-stage Vite + Python 3.12-slim
- **Claude Artifact** — 1 198-line single-file React JSX usable directly in Claude

#### Quality
- **244 Python tests** — unit + integration (pytest, Hypothesis 2000-example fuzz on all 7 parsers)
- **50 JavaScript tests** — store.js 100% coverage, ws-client.js 96% (Vitest + jsdom)
- **mypy --strict** — 0 errors on 67 source files
- **ruff** — 0 errors

[Unreleased]: https://github.com/model-story/model-story/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/model-story/model-story/releases/tag/v0.1.0
