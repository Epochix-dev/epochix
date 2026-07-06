# Epochix — System Design & Architecture

> **A visual storytelling platform for deep learning training runs.**
> Turns terminal-output logs into an animated, plain-English narrative anyone can read.

**Version:** 1.0 (Architecture Specification)
**Status:** Pre-implementation
**License (planned):** Apache-2.0
**Package name (planned):** `epochix` (PyPI) / `@epochix/web` (npm, optional)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Principles](#2-design-principles)
3. [System Overview](#3-system-overview)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Core Components](#5-core-components)
6. [Data Flow](#6-data-flow)
7. [Data Models & Schemas](#7-data-models--schemas)
8. [Storage Layer](#8-storage-layer)
9. [Parser Subsystem](#9-parser-subsystem)
10. [Story Engine](#10-story-engine)
11. [Live Streaming Subsystem](#11-live-streaming-subsystem)
12. [Frontend Architecture](#12-frontend-architecture)
13. [Visualization Engine](#13-visualization-engine)
14. [Export Pipeline](#14-export-pipeline)
15. [Public APIs](#15-public-apis)
16. [Plugin & Extension System](#16-plugin--extension-system)
17. [Integrations](#17-integrations)
18. [Deployment Topologies](#18-deployment-topologies)
19. [Performance & Scaling](#19-performance--scaling)
20. [Security, Privacy & Compliance](#20-security-privacy--compliance)
21. [Testing Strategy](#21-testing-strategy)
22. [Project Structure](#22-project-structure)
23. [Tech Stack](#23-tech-stack)
24. [Roadmap & Milestones](#24-roadmap--milestones)
25. [Distribution & Release Plan](#25-distribution--release-plan)
26. [Open Decisions](#26-open-decisions)
27. [Implementation Surfaces](#27-implementation-surfaces)
28. [Appendix A — Sample Log Signatures](#appendix-a--sample-log-signatures)
29. [Appendix B — Metaphor Library](#appendix-b--metaphor-library)

---

## 1. Executive Summary

**Epochix** ingests raw training output from any deep-learning framework and renders a live, animated, non-technical narrative of what the model is learning, how confident it is, and whether it's improving. It targets the gap between:

- **Engineer-facing tools** (TensorBoard, W&B, MLflow, Aim, Comet, Neptune) which assume ML literacy, and
- **Stakeholders** (managers, clients, regulators, researchers from other fields) who need to *understand* what's happening without a ML degree.

The system is delivered as:

- A **Python package** (`pip install epochix`) — parser + server + exporter
- A **static web bundle** — frontend dashboard served by the package or exported as standalone HTML
- A **CLI** (`epochix`) — one-command UX
- An **optional hosted service** (Phase 5) — for sharing run permalinks

### Differentiators (vs. W&B / TensorBoard / MLflow / Aim / Comet / Neptune)

| Capability                            | Existing tools | Epochix |
|---------------------------------------|----------------|----------------------|
| Non-technical narrative + letter grade| ✗              | ✓                    |
| Animated living visuals (not charts)  | ✗              | ✓                    |
| Zero code changes (parses stdout)     | ✗              | ✓                    |
| Standalone shareable HTML report      | partial        | ✓                    |
| Biometric / gaze task-aware mode      | ✗              | ✓                    |
| Epoch scrubber / replay               | partial        | ✓                    |
| pip install, one command              | partial        | ✓                    |
| Embeddable iframe widget              | partial        | ✓ *(added)*          |
| Jupyter `%epochix` magic          | ✗              | ✓ *(added)*          |
| CI/CD GitHub Action                   | ✗              | ✓ *(added)*          |
| Local-first, no required account      | ✗              | ✓                    |

---

## 2. Design Principles

The architecture follows seven non-negotiable principles. Every component is checked against this list.

1. **Zero-config, zero-account by default.** A user pipes `train.py` into `epochix --live` and the browser opens. No login. No cloud. No telemetry.
2. **Local-first, optional cloud.** Everything runs offline. Hosted sharing is a strict opt-in.
3. **Format-agnostic.** Parsers are pluggable; the universal regex fallback handles anything that prints `key=value`. LLM fallback is the last resort.
4. **Stream-first.** Live mode is a first-class citizen, not an afterthought bolted on top of a file reader.
5. **Visuals as data art.** Every chart is replaceable by an animated metaphor. Charts go in a *collapsible* "engineer panel."
6. **Exports are real artifacts.** A shared HTML or PDF must look identical to the live dashboard, work offline, and survive being emailed.
7. **Embeddable everywhere.** The dashboard renders in a `<iframe>` cleanly, in a Jupyter cell cleanly, in a Notion/Confluence page cleanly. One viewer, many surfaces.

---

## 3. System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         INPUT SURFACES                                │
│   stdin pipe   │   tail -f file   │   Python SDK   │   uploaded log  │
└────────┬───────┴────────┬─────────┴────────┬────────┴────────┬───────┘
         │                │                  │                 │
         ▼                ▼                  ▼                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    INGESTION & PARSING LAYER                          │
│  Format detector → Parser registry → Metric extractor → Normalizer    │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  Normalized MetricEvent stream
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       STORY ENGINE LAYER                              │
│  Phase detector │ Grader │ Narrator │ Task classifier │ Metaphor mgr │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  StoryFrame stream
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                  │
│      SQLite run store (default)  │  in-memory ring buffer (live)      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌──────────────────┐
│   REST API    │  │  WebSocket   │  │   SSE Fallback   │
│  (history,    │  │  (live push, │  │   (live push,    │
│   snapshots)  │  │   bidir)     │  │   uni-dir)       │
└───────┬───────┘  └──────┬───────┘  └────────┬─────────┘
        │                 │                   │
        └─────────────────┴───────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                                 │
│  Web dashboard  │  Jupyter widget  │  HTML export  │  PDF deck       │
└──────────────────────────────────────────────────────────────────────┘
```

### Six-Stage Pipeline

| Stage             | Responsibility                                  | Output type       |
|-------------------|-------------------------------------------------|-------------------|
| 1. Ingestion      | Read bytes from any source                      | `RawLogLine`      |
| 2. Parsing        | Recognize format, extract key-value pairs       | `RawMetric`       |
| 3. Normalization  | Canonical metric names, units, types            | `MetricEvent`     |
| 4. Story          | Phase / grade / metaphor / milestone detection  | `StoryFrame`      |
| 5. Storage        | Append to SQLite + ring buffer                  | `Run` object      |
| 6. Presentation   | Render visuals, narrative, exports              | UI / file         |

---

## 4. High-Level Architecture

### 4.1 Component Diagram

```
                          ╔══════════════════════════════╗
                          ║     CLIENT (Browser)         ║
                          ║                              ║
                          ║  ┌────────────────────────┐  ║
                          ║  │  Vite + Vanilla JS     │  ║
                          ║  │  ┌──────────────────┐  │  ║
                          ║  │  │  store.js        │  │  ║
                          ║  │  │  (reactive)      │  │  ║
                          ║  │  └────┬─────────────┘  │  ║
                          ║  │       │                │  ║
                          ║  │  ┌────▼──────┐ ┌─────┐ │  ║
                          ║  │  │ ws-client │ │ SSE │ │  ║
                          ║  │  └────┬──────┘ └──┬──┘ │  ║
                          ║  │       │           │   │  ║
                          ║  │  ┌────▼───────────▼─┐ │  ║
                          ║  │  │ Visualizations   │ │  ║
                          ║  │  │ Panels / Themes  │ │  ║
                          ║  │  └──────────────────┘ │  ║
                          ║  └────────────────────────┘  ║
                          ╚════════════╤═════════════════╝
                                       │ WSS / HTTPS
                          ╔════════════▼═════════════════╗
                          ║     SERVER (FastAPI)         ║
                          ║                              ║
                          ║  ┌───────────────────────┐   ║
                          ║  │  Router               │   ║
                          ║  │  /api/runs            │   ║
                          ║  │  /api/snapshot        │   ║
                          ║  │  /ws/live             │   ║
                          ║  │  /sse/live            │   ║
                          ║  └────┬──────────────────┘   ║
                          ║       │                       ║
                          ║  ┌────▼─────────────────┐    ║
                          ║  │  Hub (broadcaster)   │    ║
                          ║  │  per-run channels    │    ║
                          ║  └────┬─────────────────┘    ║
                          ║       │                       ║
                          ║  ┌────▼─────┐ ┌────────────┐ ║
                          ║  │ Ingester │ │ StoryEngine│ ║
                          ║  └────┬─────┘ └─────┬──────┘ ║
                          ║       └──────┬──────┘        ║
                          ║              │                ║
                          ║  ┌───────────▼────────────┐  ║
                          ║  │  RunStore (SQLite)     │  ║
                          ║  └────────────────────────┘  ║
                          ╚══════════════════════════════╝
                                       ▲
                                       │ stdin / tail / SDK
                          ╔════════════╧═════════════════╗
                          ║   TRAINING PROCESS           ║
                          ║   python train.py            ║
                          ╚══════════════════════════════╝
```

### 4.2 Process Boundaries

- **The training process** is *never* coupled to the dashboard. Crashing the dashboard cannot crash training.
- **The server** is one process; horizontal scaling is via Redis pub/sub (Phase 5 only).
- **The browser** holds zero authoritative state — server is the source of truth; the browser caches a snapshot + tail.

### 4.3 Three Operating Modes

| Mode         | Trigger                                | Storage              | Network |
|--------------|----------------------------------------|----------------------|---------|
| **Batch**    | `epochix train.log`                | SQLite               | local   |
| **Live**     | `python train.py 2>&1 \| epochix --live` | SQLite + RAM ring buffer | WS/SSE  |
| **Embed**    | `<iframe src=".../v/<run_id>">`        | SQLite (read-only)   | HTTPS   |

---

## 5. Core Components

### 5.1 Component Catalog

| Component             | Language       | Responsibility                                    |
|-----------------------|----------------|---------------------------------------------------|
| `cli`                 | Python         | Entry-point, arg parsing, mode dispatch           |
| `ingester`            | Python (async) | Stdin reader, file tailer, SDK receiver           |
| `parsers.*`           | Python         | Framework-specific format recognizers             |
| `parsers.universal`   | Python         | Regex fallback                                    |
| `parsers.llm`         | Python         | LLM-assisted fallback (Ollama / OpenAI)           |
| `normalizer`          | Python         | Canonicalizes metric names, units, types          |
| `story_engine`        | Python         | Phase, grade, narrative, metaphor, milestone     |
| `task_classifier`     | Python         | Detects task type from metric set                 |
| `run_store`           | Python (SQLAlchemy) | SQLite persistence                           |
| `hub`                 | Python (asyncio) | In-memory pub/sub for WS/SSE clients            |
| `server`              | Python (FastAPI) | REST + WebSocket + SSE                          |
| `exporter.html`       | Python         | Self-contained HTML bundle                        |
| `exporter.pdf`        | Python         | WeasyPrint-based slide deck                       |
| `frontend`            | JS (Vanilla + Vite) | UI shell, panels, themes                     |
| `viz.*`               | JS (Canvas/SVG/D3) | Brain, Meter, Radar, Waterfall, Scrubber     |
| `sdk` (Python)        | Python         | `LiveReporter`, `parse`, `visualize`              |
| `sdk` (JS, opt.)      | TypeScript     | `@epochix/embed` for custom integrations      |
| `jupyter_ext`         | Python         | `%epochix` cell magic                         |
| `gh_action`           | YAML + Node    | GitHub Action for CI                              |

### 5.2 Dependency Graph (Python)

```
cli ──► server ──► hub ──► run_store ──► (SQLite)
 │       │          ▲
 │       │          │
 │       └──► ingester ──► parsers.* ──► normalizer ──► story_engine ──► task_classifier
 │
 ├──► exporter.html ──► run_store
 └──► exporter.pdf  ──► run_store
```

---

## 6. Data Flow

### 6.1 Batch Mode (finished log file)

```
┌─────────────┐
│ train.log   │
└──────┬──────┘
       │ open(), readlines()
       ▼
┌─────────────────────┐
│ Ingester            │
│  - stream lines     │
└──────┬──────────────┘
       │  RawLogLine
       ▼
┌─────────────────────┐    ┌──────────────────────┐
│ Format detector     │───►│ Parser registry      │
│ (sniff first 50)    │    │  pick best parser    │
└─────────────────────┘    └──────┬───────────────┘
                                  │ RawMetric
                                  ▼
                          ┌──────────────────────┐
                          │ Normalizer           │
                          │  canonical names     │
                          └──────┬───────────────┘
                                 │ MetricEvent
                                 ▼
                          ┌──────────────────────┐
                          │ Story engine         │
                          │  phase/grade/story   │
                          └──────┬───────────────┘
                                 │ StoryFrame
                                 ▼
                          ┌──────────────────────┐
                          │ RunStore (SQLite)    │
                          └──────┬───────────────┘
                                 │
                                 ▼
                          ┌──────────────────────┐
                          │ Open browser at      │
                          │ http://127.0.0.1:7860│
                          │ /v/<run_id>          │
                          └──────────────────────┘
```

### 6.2 Live Mode (streaming via stdin)

```
   training process
        │ writes to stdout
        ▼
┌──────────────────┐
│ stdin reader     │  asyncio + aioread
│ (non-blocking)   │
└──────┬───────────┘
       │ RawLogLine (one per training line)
       ▼
┌──────────────────┐
│ Parser           │  same as batch
└──────┬───────────┘
       │
       ▼  every parsed metric event
┌──────────────────┐    ┌──────────────────────────────────┐
│ Story engine     │───►│ RunStore (write-through)         │
└──────┬───────────┘    └──────────────────────────────────┘
       │ StoryFrame
       ▼
┌──────────────────┐    fan-out
│ Hub              │ ─────────────────► WS clients
│ (per-run topic)  │ ─────────────────► SSE clients
│  + ring buffer   │ ─────────────────► (future) Redis bus
└──────────────────┘
```

**Live invariants:**
- Bounded per-client queue (default 256 messages). On overflow → coalesce by replacing the oldest *non-milestone* events with the newest.
- Heartbeat every 15 s (`{"type":"ping"}`) to detect dead clients.
- On reconnect, the client sends `last_seq`; server replays from ring buffer or DB.

### 6.3 Snapshot + Delta Protocol

This is the modern pattern that keeps dashboards responsive on first paint:

```
Client opens /v/<run_id>
       │
       ├─► GET /api/snapshot/<run_id>     [HTTP, cacheable]
       │       └─► returns: full StoryFrame list up to last epoch
       │
       └─► WS /ws/live/<run_id>?last_seq=N [persistent]
               └─► server replays seq > N from ring buffer, then live tail
```

The frontend renders the snapshot instantly (no spinner), then animates new frames as they arrive. **Time-to-first-meaningful-paint < 300 ms** on a local machine.

### 6.4 Export Flow

```
epochix export run.log --format html
        │
        ▼
┌─────────────────────┐
│ Re-parse (or load   │
│  from RunStore)     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Build single-file   │
│  HTML:              │
│  - inline CSS       │
│  - inline JS bundle │
│  - inline run JSON  │
│  - inline fonts     │
│   (base64)          │
└──────┬──────────────┘
       │
       ▼
report.html  (offline, <2MB target)
```

---

## 7. Data Models & Schemas

All Python models are Pydantic v2; all DB tables are SQLAlchemy 2.0.

### 7.1 `RawLogLine`

```python
class RawLogLine(BaseModel):
    seq: int                          # monotonic, per-run
    timestamp: datetime               # ingest time
    source: Literal["stdin","file","sdk"]
    text: str                         # raw line, untouched
```

### 7.2 `RawMetric` (parser output)

```python
class RawMetric(BaseModel):
    seq: int
    epoch: float | None
    step: int | None
    key: str                          # parser-native key, e.g. "val_acc"
    value: float | str
    parser_name: str
    confidence: float                 # 0.0–1.0, parser self-reported
```

### 7.3 `MetricEvent` (normalized)

```python
class MetricEvent(BaseModel):
    run_id: str
    seq: int
    timestamp: datetime
    epoch: float | None
    step: int | None
    canonical_key: str                # one of: train_loss, val_loss, accuracy,
                                      # val_accuracy, lr, mAP50, mAP, MAE, RMSE,
                                      # f1, precision, recall, perplexity, bleu,
                                      # EER, TAR_at_FAR_0_001, epoch_time, eta, custom
    raw_key: str                      # original
    value: float
    unit: str | None                  # "%", "px", "deg", "ms", "s"
    task_hint: TaskType | None        # classification|detection|regression|biometric|nlp|custom
```

### 7.4 `StoryFrame` (story engine output)

```python
class StoryFrame(BaseModel):
    run_id: str
    seq: int
    epoch: float | None
    progress: float                   # 0.0–1.0 estimated
    phase: Phase                      # see enum below
    grade: Grade                      # current letter
    primary_metric_value: float
    confidence: float                 # 0.0–1.0 for hero visuals
    narrative: str                    # short paragraph
    metaphor_cards: list[MetaphorCard]
    skill_dimensions: dict[str, float] # for radar
    milestones: list[Milestone]       # any new ones reached this frame
    warnings: list[Warning]           # overfit/diverge/plateau
    task_type: TaskType
```

### 7.5 Enums

```python
class Phase(str, Enum):
    AWAKENING = "awakening"        # 0–10% progress
    LEARNING = "learning"          # 10–40%
    UNDERSTANDING = "understanding"# 40–70%
    MASTERING = "mastering"        # 70–95%
    POLISHING = "polishing"        # 95–100%

class Grade(str, Enum):
    A_PLUS = "A+"; A = "A"; A_MINUS = "A-"
    B_PLUS = "B+"; B = "B"; B_MINUS = "B-"
    C_PLUS = "C+"; C = "C"; C_MINUS = "C-"
    D = "D"; F = "F"
    INCOMPLETE = "I"

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    DETECTION = "detection"
    REGRESSION = "regression"
    BIOMETRIC = "biometric"
    GAZE = "gaze"
    NLP = "nlp"
    GENERATIVE = "generative"
    CUSTOM = "custom"
```

### 7.6 `Run`

```python
class Run(BaseModel):
    id: str                           # ULID
    name: str | None
    task_type: TaskType
    started_at: datetime
    finished_at: datetime | None
    primary_metric: str               # canonical key for grading
    framework_detected: str | None    # "pytorch_lightning" etc.
    parser_used: str
    total_epochs_est: int | None
    final_grade: Grade | None
    story_summary: str | None
    config: dict[str, Any]            # user config snapshot
```

### 7.7 SQLite Schema (DDL)

```sql
CREATE TABLE runs (
  id              TEXT PRIMARY KEY,
  name            TEXT,
  task_type       TEXT NOT NULL,
  started_at      DATETIME NOT NULL,
  finished_at     DATETIME,
  primary_metric  TEXT NOT NULL,
  framework       TEXT,
  parser_used     TEXT,
  total_epochs    INTEGER,
  final_grade     TEXT,
  story_summary   TEXT,
  config_json     TEXT
);

CREATE TABLE metric_events (
  run_id          TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  ts              DATETIME NOT NULL,
  epoch           REAL,
  step            INTEGER,
  canonical_key   TEXT NOT NULL,
  raw_key         TEXT NOT NULL,
  value           REAL NOT NULL,
  unit            TEXT,
  PRIMARY KEY (run_id, seq),
  FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE INDEX idx_metric_run_epoch ON metric_events(run_id, epoch);
CREATE INDEX idx_metric_run_key   ON metric_events(run_id, canonical_key);

CREATE TABLE story_frames (
  run_id          TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  epoch           REAL,
  progress        REAL,
  phase           TEXT,
  grade           TEXT,
  primary_value   REAL,
  confidence      REAL,
  narrative       TEXT,
  metaphor_json   TEXT,
  skill_json      TEXT,
  warnings_json   TEXT,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE milestones (
  run_id          TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  kind            TEXT NOT NULL,    -- e.g. "first_above_50", "best_so_far"
  epoch           REAL,
  value           REAL,
  message         TEXT,
  PRIMARY KEY (run_id, seq, kind)
);

CREATE TABLE raw_lines (
  run_id          TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  ts              DATETIME NOT NULL,
  text            TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
```

**Storage notes:**
- SQLite with WAL mode → safe for concurrent reader + writer.
- For very long runs (>100k epochs), `raw_lines` can be opt-in (`--keep-raw`).
- Inspired by **MLtraq** and **Aim**, which benchmark 20–400× faster than W&B/MLflow for high-frequency writes; we avoid threading and append directly with `INSERT … ON CONFLICT DO NOTHING`.

---

## 8. Storage Layer

### 8.1 Primary Store — SQLite

- Default path: `~/.epochix/runs.db`
- Configurable via `EPOCHIX_DB` env var or `--db` flag.
- WAL mode, `synchronous=NORMAL`, `journal_size_limit=64MB`.
- Single file. Easy to commit, email, or delete.

### 8.2 In-memory Ring Buffer (live mode only)

- `collections.deque(maxlen=2048)` per active run.
- Holds the last N `StoryFrame`s for fast reconnect / catch-up.
- Discarded on server restart (DB is authoritative).

### 8.3 Optional Redis (Phase 5, multi-worker)

- Pub/sub channel: `epochix:run:<run_id>`.
- Used only when running behind a load balancer with multiple Uvicorn workers.

### 8.4 Retention & Cleanup

- `epochix prune --older-than 30d` — deletes runs.
- `epochix compact` — runs `VACUUM` + rebuilds indices.
- No automatic deletion. The user owns the data.

---

## 9. Parser Subsystem

### 9.1 Three-Layer Strategy

```
Line ──► [1] Structured parsers (regex, fast)
         │     ├─ pytorch_lightning
         │     ├─ keras_tensorflow
         │     ├─ huggingface
         │     ├─ ultralytics_yolo
         │     ├─ fastai
         │     ├─ catalyst
         │     └─ accelerate
         │     ▼ no match
         │  [2] Universal regex fallback
         │     (matches "key=value", "key: value", "key value", JSON dicts)
         │     ▼ no metrics extracted
         │  [3] LLM-assisted parser (opt-in)
         │     ├─ Ollama (local default — llama3.1:8b or qwen2.5:7b)
         │     └─ OpenAI / Anthropic API (opt-in)
         ▼
       RawMetric
```

### 9.2 Parser Interface

```python
class BaseParser(Protocol):
    name: str
    priority: int                          # higher wins on tie
    def sniff(self, sample_lines: list[str]) -> float:
        """Confidence 0.0–1.0 that this parser owns the format."""
    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        ...
```

Parsers are **stateful per run** (e.g. PyTorch Lightning needs to know the current epoch from a header line). State is held in `ParserContext`.

### 9.3 Format Detection

On the first 50 lines (or 5 seconds in live mode), every registered parser runs `.sniff()`. The winner is locked in for the rest of the run. If sniff scores are all below 0.3, the universal fallback is used.

### 9.4 LLM Fallback

Borrowing from **LogBatcher** (FSE 2025, demonstration-free LLM log parsing): when no structured parser succeeds, batches of ~10 unknown lines are sent to a local LLM with a prompt template that asks for JSON-extracted key/value pairs. Output is validated against the `MetricEvent` schema; invalid extractions are dropped.

- Default: `ollama run qwen2.5:7b` if Ollama is reachable on `127.0.0.1:11434`.
- Opt-in: OpenAI / Anthropic via `EPOCHIX_LLM_KEY` env var.
- Disabled by default in CI / headless mode.

### 9.5 Custom Parser Registration

```python
from epochix.parsers import register_parser, BaseParser

@register_parser
class MyTrainerParser(BaseParser):
    name = "my_trainer"
    priority = 100
    def sniff(self, lines): ...
    def parse_line(self, line, ctx): ...
```

Plugin parsers can also be installed as separate PyPI packages with the entry point group `epochix.parsers`.

---

## 10. Story Engine

### 10.1 Architecture

```
MetricEvent ──► TaskClassifier ──► Phase detector ──► Grader
                                      │                  │
                                      ▼                  ▼
                                  Narrator ──► Metaphor manager
                                      │
                                      ▼
                                Milestone detector ──► StoryFrame
                                      │
                                      ▼
                                Warning detector
                                (overfit, divergence, plateau)
```

### 10.2 Task Classifier

Fires *once per run* when ≥3 metric events have arrived. Decision table:

| Detected canonical key  | Implied task          |
|-------------------------|-----------------------|
| `EER`, `TAR_at_FAR_*`   | biometric             |
| `MAE` + low value (<10) | gaze / regression     |
| `mAP*`                  | detection             |
| `perplexity` / `bleu`   | nlp                   |
| `accuracy` only         | classification        |
| `fid` / `is_score`      | generative            |
| (nothing matches)       | custom                |

Override: `epochix --task biometric`, or `LiveReporter(task="biometric")`.

### 10.3 Phase Detector

Hybrid of progress-based and metric-based:

```python
def phase(progress: float, primary: float, baseline: float) -> Phase:
    if progress < 0.10: return AWAKENING
    relative = (primary - baseline) / (target - baseline + 1e-9)
    if progress < 0.40 or relative < 0.40: return LEARNING
    if progress < 0.70 or relative < 0.75: return UNDERSTANDING
    if progress < 0.95 or relative < 0.95: return MASTERING
    return POLISHING
```

### 10.4 Grader

Task-specific thresholds, configurable via `.epochix.yaml`:

```yaml
grade_thresholds:
  classification:
    A_plus: 0.95
    A:      0.90
    B_plus: 0.82
    B:      0.75
    C:      0.65
    D:      0.50
  biometric:        # uses EER (lower=better)
    A_plus: 0.01
    A:      0.03
    B_plus: 0.05
    B:      0.10
    C:      0.20
    D:      0.30
```

### 10.5 Narrator

Deterministic template engine; **no LLM in the hot path** for reproducibility and offline use.

```python
def narrate(frame: StoryFrame, prev: StoryFrame | None) -> str:
    tpl = TEMPLATES[frame.task_type][frame.phase]
    delta = frame.primary_metric_value - (prev.primary_metric_value if prev else 0)
    return tpl.format(
        epoch=frame.epoch,
        value=fmt(frame.primary_metric_value, frame.task_type),
        delta=fmt(delta, frame.task_type),
        emoji=PHASE_EMOJI[frame.phase],
    )
```

Templates live in `story_engine/templates/{task}/{phase}.txt` and are i18n-able (`{task}.fa.txt`, `{task}.fr.txt`).

### 10.6 Milestone Detection

Detected milestones (each fires at most once per run):

| Kind                       | Trigger                                  |
|----------------------------|------------------------------------------|
| `first_above_25/50/75/90`  | primary metric crosses threshold         |
| `best_so_far`              | new max (or min for loss/EER)            |
| `biggest_jump`             | top-1 single-epoch Δ at end of run       |
| `overfit_warning`          | val_loss rising 3 epochs while train↓    |
| `plateau`                  | <1% improvement over last 5 epochs       |
| `lr_drop`                  | learning rate decreased                  |
| `divergence`               | loss NaN or >10× previous                |
| `training_complete`        | end-of-stream                            |

### 10.7 Warning System

Warnings appear as amber cards in the timeline. Examples:

- *"The model may be memorising the study material instead of understanding it."* — overfit
- *"Learning has slowed. The model has stopped finding new patterns."* — plateau
- *"Something went wrong — the model's score has spiked. The teacher may need to lower the learning rate."* — divergence

---

## 11. Live Streaming Subsystem

### 11.1 Channel Model

Per run, a single broadcast channel. Clients subscribe on connect with `?run_id=<id>` and optionally `?last_seq=<n>` to resume.

### 11.2 Message Envelope

```json
{
  "v": 1,
  "type": "story_frame" | "milestone" | "warning" | "complete" | "ping",
  "run_id": "01J...",
  "seq": 42,
  "ts": "2026-05-15T12:34:56Z",
  "payload": { ... }
}
```

### 11.3 Backpressure & Slow Consumers

- Each client has a bounded `asyncio.Queue(maxsize=256)`.
- On full: oldest non-milestone frames are dropped (coalesced). Milestones and warnings are **never dropped**.
- A slow client cannot block the hub.

### 11.4 Reconnection

Client uses exponential backoff: 1 s → 2 → 4 → 8 → max 30 s. On reconnect, sends last-known `seq`; server replays from ring buffer (or queries DB if older than buffer).

### 11.5 Protocol Tiers

| Protocol  | Use case                          | Fallback role  |
|-----------|-----------------------------------|----------------|
| WebSocket | Default — bidirectional, scrubbing| Primary        |
| SSE       | Behind strict corporate proxies   | Fallback       |
| Polling   | Extreme constrained networks      | Emergency      |

The client tries WS → falls back to SSE → falls back to 2 s polling.

---

## 12. Frontend Architecture

### 12.1 Stack

- **Build:** Vite 5 (tree-shaken, single-file build for HTML export).
- **Framework:** None. Vanilla JS + a 50-line reactive store (signals).
- **Charts:** Chart.js for the engineer panel; D3 (just the path/scale modules) for the radar.
- **Animations:** Native HTML5 Canvas API + CSS `@property` animated gradients. Zero animation library dependency.
- **Icons:** Lucide (UMD).
- **Fonts:** DM Sans + Instrument Serif (Google Fonts, embedded as base64 in HTML export).
- **Styling:** CSS custom properties; no Tailwind in the runtime (Tailwind is fine for dev but compiled into plain CSS for export).

> **Why no React/Vue?** A frame-rate-critical, embeddable widget benefits from the smaller bundle (target: < 200 KB gzipped) and tighter control of the render loop. Many of the visualizations bypass the DOM entirely (canvas), so framework reactivity adds cost without benefit.

### 12.2 Reactive Store

```js
// store.js — minimal signals-based store, ~50 LOC
export const createStore = (initial) => {
  let state = initial;
  const subs = new Set();
  return {
    get: () => state,
    set: (patch) => { state = { ...state, ...patch }; subs.forEach(f => f(state)); },
    subscribe: (fn) => { subs.add(fn); return () => subs.delete(fn); },
  };
};
```

Visualizations subscribe directly and run their own `requestAnimationFrame` loop.

### 12.3 Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│ HEADER  [run name]   [grade pill]   [phase emoji]   [time]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────────────────┐    ┌──────────────────────────┐  │
│   │                      │    │  STORY (narrator text)   │  │
│   │   BRAIN CANVAS       │    │                          │  │
│   │   (hero, animated)   │    │  Cards (4 metaphors)     │  │
│   │                      │    │                          │  │
│   └──────────────────────┘    └──────────────────────────┘  │
│                                                             │
│   ┌──────────────────────┐    ┌──────────────────────────┐  │
│   │ CONFIDENCE LIQUID    │    │  SKILL RADAR             │  │
│   └──────────────────────┘    └──────────────────────────┘  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │  TIMELINE (milestone cards, scrub control below)    │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │  ENGINEER PANEL (collapsed by default)              │  │
│   │   loss / val_loss / lr / Chart.js                   │  │
│   └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 12.4 Theming

Two themes by default (`light`, `dark`), driven by CSS custom properties. Brand customization lives in one file (`themes/custom.css`). The export bundle inlines the active theme.

### 12.5 Embedding API

```html
<iframe
  src="https://your-host/v/01J.../embed?panel=hero&theme=dark"
  width="900" height="600" loading="lazy">
</iframe>
```

The `?panel=` query param lets you embed *only* the hero visual, or only the timeline, etc.

---

## 13. Visualization Engine

### 13.1 Catalog

| Viz                   | Tech            | Driven by              | Priority |
|-----------------------|-----------------|------------------------|----------|
| Brain Canvas          | Canvas 2D       | `confidence`, `phase`  | P0       |
| Confidence Liquid     | SVG + CSS       | `primary_metric_value` | P1       |
| Skill Radar           | D3 path morph   | `skill_dimensions`     | P1       |
| Timeline Story Cards  | DOM (animated)  | `milestones`           | P0       |
| Improvement Waterfall | Canvas particles| Δ per epoch            | P2       |
| Grade Card            | DOM + CSS keys  | `grade`                | P0       |
| Epoch Scrubber        | DOM + range     | `current_seq`          | P1       |
| Engineer Charts       | Chart.js        | `metric_events`        | P0       |

### 13.2 Animation Loop Pattern

Every canvas visualization owns its `requestAnimationFrame` loop. It reads from the reactive store on each frame and never mutates the store from inside the loop. This keeps the data flow strictly one-way and avoids feedback loops.

```js
function loop(t) {
  const s = store.get();
  ctx.clearRect(0, 0, w, h);
  draw(ctx, s, t);
  raf = requestAnimationFrame(loop);
}
```

### 13.3 Performance Budget

| Metric                    | Budget        |
|---------------------------|---------------|
| Bundle size (gzipped)     | < 200 KB      |
| HTML export size          | < 2 MB        |
| First meaningful paint    | < 300 ms (local)  |
| Steady-state frame rate   | ≥ 50 fps      |
| Memory ceiling (60-epoch run) | < 80 MB |

Brain canvas auto-throttles to 30 fps when the tab is backgrounded.

---

## 14. Export Pipeline

### 14.1 HTML Export

```
epochix export run.log --format html --output report.html
```

- Vite builds a `single-file` bundle (all CSS/JS inlined as data URIs).
- Run data is inlined as `<script type="application/json" id="run-data">…</script>`.
- Fonts are base64-embedded.
- Result: one HTML file, no network requests at view time, fully animated.
- Target size: **< 2 MB** including fonts.

### 14.2 PDF Slide Deck

```
epochix export run.log --format pdf --output report.pdf
```

- One slide per major milestone + final summary slide.
- Uses **WeasyPrint** (CSS-driven page layout). All visuals are pre-rendered to SVG.
- Pages: cover → phase summaries → final grade → engineer appendix.

### 14.3 Standalone JSON Run

```
epochix export run.log --format json --output run.json
```

The full canonical run, ready to be re-imported elsewhere.

### 14.4 Markdown Summary (added)

```
epochix export run.log --format md --output report.md
```

Plain-English narrative + grade + key milestones. Useful for inclusion in PR descriptions, papers, status reports.

---

## 15. Public APIs

### 15.1 Command Line

```
epochix <log_file>                  # batch view
epochix --live                      # read stdin
epochix --live --tail FILE          # tail mode
epochix --port 7860                 # change port
epochix --task biometric            # force task
epochix --no-llm                    # disable LLM fallback
epochix --headless --export html    # CI mode, no browser
epochix compare run1.log run2.log   # side-by-side
epochix prune --older-than 30d
epochix compact
epochix list                        # list saved runs
epochix open <run_id>               # open a saved run
epochix config show|set <k> <v>
```

### 15.2 Python SDK

```python
from epochix import parse, visualize, LiveReporter

# 1. Parse a file
run = parse("train.log", task="biometric")
print(run.final_grade)       # "A-"
print(run.story_summary)     # "The model learned to distinguish..."
visualize(run)               # opens browser

# 2. Live reporting (no log parsing needed)
reporter = LiveReporter(
    task="gaze",
    primary_metric="mae",
    name="gazeformer_v7",
)
for ep in range(100):
    loss, mae = train_epoch()
    reporter.log(epoch=ep, train_loss=loss, mae=mae)
reporter.finish()

# 3. Compare runs
from epochix import compare
diff = compare("run_v1.json", "run_v2.json")
diff.show()
```

### 15.3 REST API (server)

| Method | Path                          | Purpose                           |
|--------|-------------------------------|-----------------------------------|
| GET    | `/api/runs`                   | List runs                         |
| GET    | `/api/runs/{id}`              | Run metadata                      |
| GET    | `/api/snapshot/{id}`          | Full StoryFrame list (cacheable)  |
| GET    | `/api/metrics/{id}`           | Raw metric events                 |
| GET    | `/api/raw/{id}`               | Raw log lines (if retained)       |
| POST   | `/api/runs/{id}/event`        | SDK push endpoint                 |
| DELETE | `/api/runs/{id}`              | Delete a run                      |
| GET    | `/api/export/{id}/html`       | Generate HTML report on demand    |
| GET    | `/api/export/{id}/pdf`        | Generate PDF report on demand     |
| GET    | `/api/health`                 | Liveness probe                    |
| GET    | `/api/version`                | Server version + build hash       |

### 15.4 WebSocket API

`WS /ws/live/{run_id}?last_seq={n}` — see §11.

### 15.5 SSE API

`GET /sse/live/{run_id}?last_seq={n}` — event types match WS message envelope.

---

## 16. Plugin & Extension System

### 16.1 Entry-Point Groups

| Group                       | Purpose                            |
|-----------------------------|-------------------------------------|
| `epochix.parsers`       | Custom parser classes               |
| `epochix.metaphor_packs`| Domain-specific narrative templates |
| `epochix.exporters`     | Additional export formats           |
| `epochix.tasks`         | Custom task types (define grading)  |

### 16.2 Example Plugin Package

```toml
# pyproject.toml
[project.entry-points."epochix.parsers"]
fairseq = "epochix_fairseq:FairseqParser"
```

```python
from epochix.parsers import BaseParser, register_parser

@register_parser
class FairseqParser(BaseParser):
    name = "fairseq"
    priority = 50
    def sniff(self, lines): ...
    def parse_line(self, line, ctx): ...
```

### 16.3 Metaphor Pack Example

```yaml
# medical_imaging.yaml
name: medical_imaging
task_aliases: [medical, radiology, segmentation]
phases:
  awakening:
    template: |
      The model is just being shown its first scans. Like a first-year
      radiology resident, it's overwhelmed by what it sees.
  mastering: ...
```

---

## 17. Integrations

### 17.1 Jupyter / Colab Cell Magic

```python
%load_ext epochix
%epochix train.log
# or live:
%%epochix --live
!python train.py
```

Renders an iframe in the cell output (or an inline div). Works offline in Colab.

### 17.2 GitHub Action

```yaml
# .github/workflows/training.yml
- name: Train and report
  run: python train.py 2>&1 | tee train.log
- uses: epochix/action@v1
  with:
    log: train.log
    upload-html: true
- name: Comment on PR
  uses: epochix/comment-action@v1
  with:
    summary: report.md
```

The action generates `report.html` and `report.md` and posts the narrative as a PR comment.

### 17.3 PyTorch Lightning Callback

```python
from epochix.integrations.lightning import StoryCallback

trainer = pl.Trainer(callbacks=[StoryCallback(task="classification")])
```

### 17.4 HuggingFace Trainer Callback

```python
from epochix.integrations.hf import StoryCallback

trainer = Trainer(callbacks=[StoryCallback(task="nlp")], ...)
```

### 17.5 TensorBoard / W&B Bridge

```
epochix import-tensorboard ./runs/
epochix import-wandb <api_key> <run_id>
```

Lets you backfill existing runs.

### 17.6 OpenTelemetry (production observability — added)

The server emits OTLP traces for each WS connection, parse operation, and export. Useful for teams running the hosted version at scale.

---

## 18. Deployment Topologies

### 18.1 Local (default)

- Single process, SQLite, no auth.
- `epochix --live` binds to `127.0.0.1:7860`.

### 18.2 Team server (LAN)

- `--host 0.0.0.0 --auth basic` or `--auth token`.
- SQLite still fine for tens of users.

### 18.3 Hosted / shared (Phase 5)

```
                ┌──────────────────────────┐
                │   NGINX / Caddy (TLS)    │
                └──────────┬───────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ Uvicorn │  │ Uvicorn │  │ Uvicorn │
        │ worker  │  │ worker  │  │ worker  │
        └────┬────┘  └────┬────┘  └────┬────┘
             └────────────┼────────────┘
                          ▼
                 ┌────────────────┐
                 │  Redis pub/sub │
                 │  (fan-out)     │
                 └────────────────┘
                          │
                          ▼
                 ┌────────────────┐
                 │  Postgres      │
                 │  (runs + index)│
                 └────────────────┘
```

- Postgres for multi-user run history; per-run metric events can still go to a separate columnar store (DuckDB/Parquet on S3) for very long runs.
- Authentication: OAuth (GitHub) or JWT.
- Per-run shareable permalinks with optional public/private/team scope.

### 18.4 Docker / Devcontainer

A `docker-compose.yml` ships in the repo: server + Redis + Postgres + an optional Ollama container. `make dev` runs the full stack.

---

## 19. Performance & Scaling

### 19.1 Targets

| Metric                                  | Target               |
|-----------------------------------------|----------------------|
| Parse throughput                        | ≥ 50k lines/sec      |
| Live latency (parse → browser render)   | < 500 ms p95         |
| First meaningful paint                  | < 300 ms (local)     |
| WS connections per worker               | ≥ 1000 concurrent    |
| Memory per run (in flight)              | < 30 MB              |
| SQLite write rate                       | ≥ 10k events/sec     |
| Bundle size (gzipped)                   | < 200 KB             |

### 19.2 Hot Paths

1. **Parser** — regex precompiled once, no per-line allocation.
2. **Story engine** — avoid full DB round-trips; cache prev frame in memory per run.
3. **WS hub** — single-producer, multi-consumer; messages are pre-serialized once.

### 19.3 Profiling

- `pytest --benchmark` for parser micro-benchmarks.
- `py-spy` flame graphs in CI on every PR for the parse pipeline.
- Client-side: Lighthouse + custom RUM for frame rate / TTI.

---

## 20. Security, Privacy & Compliance

### 20.1 Threat Model

- Default local mode: trust boundary is the user's machine. No threats from network.
- Hosted mode: standard web threat model (CSRF, XSS, IDOR, auth bypass).

### 20.2 Privacy

- No telemetry by default. Opt-in via `epochix config set telemetry true`.
- LLM fallback is **disabled** unless explicitly enabled. Local Ollama preferred.
- Run data never leaves the machine in local mode.

### 20.3 Sanitization

- Raw log lines may contain secrets (API keys printed by accident). The optional `--scrub` flag runs an entropy-based secret scrubber (gitleaks-style regex) before persisting.

### 20.4 Authentication (hosted)

- OAuth (GitHub, Google) or JWT.
- Per-run ACL: `private` / `team` / `public-link` / `public-listed`.

### 20.5 Compliance

- All run data deletable in one CLI command. Useful for GDPR "right to erasure" if a hosted deployment touches EU data.
- SBOM (CycloneDX) shipped with each release.

---

## 21. Testing Strategy

| Layer            | Framework         | Coverage target |
|------------------|-------------------|-----------------|
| Parser unit      | pytest            | ≥ 95%           |
| Story engine     | pytest            | ≥ 90%           |
| API contract     | schemathesis      | 100% endpoints  |
| WS protocol      | pytest-asyncio    | core flows      |
| Frontend unit    | Vitest            | ≥ 80%           |
| Frontend E2E     | Playwright        | smoke + viz     |
| Export integrity | Playwright (HTML) | visual diff     |
| Performance      | pytest-benchmark + Lighthouse | tracked over time |

### 21.1 Sample Log Fixtures

The repo ships ~30 real-world log fixtures in `tests/fixtures/logs/` covering every supported framework, plus 5 deliberately-malformed logs for fallback testing, plus 2 domain logs from the maintainer team's own work (gaze, fingerprint) to anchor task-specific tests.

### 21.2 Property Tests

Hypothesis-based fuzz on the universal parser: any string with at least one `key=value` pattern must either parse or fall through cleanly — never crash.

---

## 22. Project Structure

```
model-learning-story/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── docker-compose.yml
├── Makefile
├── .pre-commit-config.yaml
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── release.yml
│   │   └── benchmarks.yml
│   └── actions/                       # the epochix/action repo
│
├── src/epochix/
│   ├── __init__.py
│   ├── cli.py                         # Typer-based
│   ├── config.py                      # pydantic-settings
│   ├── models.py                      # Pydantic v2 schemas
│   ├── enums.py
│   │
│   ├── ingester/
│   │   ├── __init__.py
│   │   ├── stdin.py
│   │   ├── file_tail.py
│   │   └── sdk_receiver.py
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── pytorch_lightning.py
│   │   ├── keras_tensorflow.py
│   │   ├── huggingface.py
│   │   ├── ultralytics_yolo.py
│   │   ├── fastai.py
│   │   ├── accelerate.py
│   │   ├── universal.py
│   │   └── llm_fallback.py
│   │
│   ├── normalizer/
│   │   ├── __init__.py
│   │   ├── canonical_keys.py
│   │   └── units.py
│   │
│   ├── story_engine/
│   │   ├── __init__.py
│   │   ├── narrator.py
│   │   ├── grade.py
│   │   ├── phases.py
│   │   ├── milestones.py
│   │   ├── warnings.py
│   │   ├── task_classifier.py
│   │   └── templates/
│   │       ├── classification/
│   │       ├── detection/
│   │       ├── regression/
│   │       ├── biometric/
│   │       ├── gaze/
│   │       ├── nlp/
│   │       └── generative/
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   ├── sqlite_store.py
│   │   ├── ring_buffer.py
│   │   └── migrations/
│   │
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py                     # FastAPI factory
│   │   ├── routes_runs.py
│   │   ├── routes_snapshot.py
│   │   ├── routes_export.py
│   │   ├── ws.py
│   │   ├── sse.py
│   │   ├── hub.py
│   │   └── auth.py
│   │
│   ├── sdk/
│   │   ├── __init__.py
│   │   ├── live_reporter.py
│   │   ├── parse.py
│   │   └── compare.py
│   │
│   ├── exporters/
│   │   ├── __init__.py
│   │   ├── html_export.py
│   │   ├── pdf_export.py
│   │   ├── markdown_export.py
│   │   └── json_export.py
│   │
│   ├── integrations/
│   │   ├── lightning.py
│   │   ├── hf.py
│   │   ├── jupyter.py
│   │   ├── tensorboard_import.py
│   │   └── wandb_import.py
│   │
│   └── _frontend/                     # built bundle copied in at release
│       └── dist/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.js
│   │   ├── store.js
│   │   ├── ws-client.js
│   │   ├── sse-client.js
│   │   ├── panels/
│   │   │   ├── HeroPanel.js
│   │   │   ├── JourneyPanel.js
│   │   │   ├── SkillsPanel.js
│   │   │   └── TechPanel.js
│   │   ├── visualizations/
│   │   │   ├── BrainCanvas.js
│   │   │   ├── LearningMeter.js
│   │   │   ├── ConfidenceBars.js
│   │   │   ├── SkillRadar.js
│   │   │   ├── TimelineStory.js
│   │   │   ├── ImprovementWaterfall.js
│   │   │   ├── GradeCard.js
│   │   │   ├── EpochScrubber.js
│   │   │   └── ParticleField.js
│   │   ├── themes/
│   │   │   ├── light.css
│   │   │   └── dark.css
│   │   └── i18n/
│   │       ├── en.json
│   │       ├── fa.json
│   │       └── fr.json
│   └── public/
│
├── demo/
│   ├── pytorch_lightning.log
│   ├── keras_image_classifier.log
│   ├── huggingface_bert.log
│   ├── yolov8_detection.log
│   ├── gaze_estimation.log
│   └── fingerprint_matching.log
│
├── tests/
│   ├── fixtures/
│   │   └── logs/
│   ├── unit/
│   │   ├── test_parsers.py
│   │   ├── test_normalizer.py
│   │   ├── test_story_engine.py
│   │   └── test_store.py
│   ├── integration/
│   │   ├── test_api.py
│   │   ├── test_ws.py
│   │   └── test_export.py
│   ├── e2e/                           # Playwright
│   └── benchmarks/
│
├── docs/
│   ├── index.md
│   ├── quickstart.md
│   ├── parsers.md
│   ├── plugins.md
│   ├── deployment.md
│   ├── architecture.md                # this file
│   └── screenshots/
│
└── scripts/
    ├── generate-fake-log.py
    ├── benchmark-parsers.py
    └── update-vendored-frontend.sh
```

---

## 23. Tech Stack

| Layer             | Choice                          | Reasoning                              |
|-------------------|---------------------------------|----------------------------------------|
| Language (server) | Python 3.10+                    | Universal ML ecosystem                 |
| Web framework     | FastAPI 0.116+                  | Async-first, WS native, fast           |
| ASGI server       | Uvicorn (stdlib loop)           | Production standard                    |
| Validation        | Pydantic v2                     | Speed, ergonomics                      |
| CLI               | Typer                           | Native FastAPI-style ergonomics        |
| ORM               | SQLAlchemy 2.0 (Core mode)      | SQLite + Postgres portability          |
| Settings          | pydantic-settings               | Env + file config                      |
| Logging           | structlog                       | Best-in-class for observability (2026) |
| Migrations        | Alembic                         | Standard                               |
| Concurrency       | asyncio                         | Native FastAPI                         |
| Frontend bundler  | Vite 5                          | Single-file build, fast HMR            |
| Frontend lang     | Vanilla JS + JSDoc types        | Zero framework cost                    |
| Charts            | Chart.js (engineer panel only)  | Lightweight, great defaults            |
| Radar             | D3 v7 (path module only)        | Path morphing                          |
| Animations        | Canvas 2D + CSS `@property`     | Zero animation lib                     |
| Icons             | Lucide                          | Consistent, tree-shakable              |
| Fonts             | DM Sans + Instrument Serif      | Free, beautiful, embeddable            |
| PDF               | WeasyPrint                      | CSS-driven layout                      |
| HTML inliner      | Vite `viteSingleFile` plugin    | One-file output                        |
| LLM (opt.)        | Ollama (default) / OpenAI / Anthropic | Privacy-first, flexible          |
| Cache (hosted)    | Redis                           | Pub/sub + cache                        |
| DB (hosted)       | Postgres 16                     | Standard                               |
| Reverse proxy     | NGINX / Caddy                   | TLS + WS upgrade                       |
| Tracing (opt.)    | OpenTelemetry                   | OTLP standard                          |
| Tests (Python)    | pytest + hypothesis + benchmark | Standard + property + perf             |
| Tests (frontend)  | Vitest + Playwright             | Fast + real-browser                    |
| API contract test | Schemathesis                    | Auto-generated from OpenAPI            |
| Linter            | Ruff + black                    | Speed                                  |
| Type checker      | mypy strict                     | Public API safety                      |
| Packaging         | hatch + hatchling               | PEP 621                                |
| Pre-commit        | pre-commit                      | Standard                               |
| CI                | GitHub Actions                  | Standard                               |

### 23.1 Why these vs. alternatives

- **Vanilla JS over React**: bundle size matters (HTML export is the killer feature); canvas-heavy work doesn't benefit from a vDOM.
- **SQLite over Postgres by default**: zero install, instant deletion, single file = one less moving part.
- **structlog over stdlib logging**: 2026 ecosystem winner for OpenTelemetry-native logging.
- **Ollama over OpenAI by default**: privacy, free, works offline. OpenAI as opt-in for accuracy.
- **Storage approach borrowed from MLtraq/Aim**: append-only, no threading, no per-row overhead. 20–400× faster than W&B-style architectures for high-frequency writes.

---

## 24. Roadmap & Milestones

| Week | Milestone                              | Acceptance criterion                                          |
|------|----------------------------------------|---------------------------------------------------------------|
| 1    | Repo scaffold + CI                     | `pytest -q` green; pre-commit clean                           |
| 1    | Parser v1 (5 frameworks + universal)   | Parses all 6 fixtures with ≥ 95% metric capture               |
| 2    | Story engine v1                        | Phase + grade + narrator deterministic across runs            |
| 2    | SQLite store + REST API                | Round-trip a finished log → API returns full snapshot         |
| 3    | Frontend shell + hero panel            | Brain canvas + grade card animate from real data              |
| 3    | Timeline + milestone cards             | All 8 milestone kinds fire correctly on fixtures              |
| 4    | Live mode (stdin + WS + SSE)           | Live latency < 500 ms p95 on a 100-epoch fake run             |
| 4    | Liquid fill + radar                    | Smooth path morph between epochs                              |
| 5    | Scrubber / playback                    | Drag epoch range → all visuals stay in sync                   |
| 5    | HTML export (single-file)              | < 2 MB, opens offline, animations intact                      |
| 6    | Task-aware narrator (biometric, gaze)  | Domain-correct phrasing on team fixtures                      |
| 6    | Jupyter magic                          | `%epochix` renders in Colab                               |
| 7    | PDF export + Markdown export           | One deck per run, one summary per run                         |
| 7    | Lightning + HF callbacks               | `pip install epochix[lightning]` works                    |
| 8    | Run comparison view                    | Side-by-side timelines, grade diff                            |
| 8    | GitHub Action                          | Auto-comments PRs with run summary                            |
| 9    | LLM fallback (Ollama)                  | Parses an unseen format with ≥ 70% recall                     |
| 9    | Plugin system                          | An external `epochix-fairseq` parser installs cleanly     |
| 10   | Docs + screenshots + landing page      | Quickstart works for a new user in < 60 seconds               |
| 10   | v0.1 release on PyPI                   | `pip install epochix` works on Linux/macOS/Windows        |
| 12+  | Hosted version (opt-in)                | Sign in, push runs, get a permalink                           |

### 24.1 Definition of Done — v0.1

- `pip install epochix` works on Python 3.10/3.11/3.12 on Linux/macOS/Windows.
- `epochix <any of 6 demo logs>` opens a complete dashboard.
- `python fake_train.py | epochix --live` works end-to-end.
- `epochix export train.log --format html` produces an offline file < 2 MB.
- README has a 20-second video demo.
- A non-ML person can describe the model's state after viewing the dashboard for 30 seconds.

---

## 25. Distribution & Release Plan

### 25.1 PyPI

- Versioning: SemVer. v0.x = pre-stable.
- Wheels built per OS via GitHub Actions.
- Frontend bundle is **vendored** into the wheel at build time so no `npm` needed on install.

### 25.2 Optional npm packages

- `@epochix/embed` — tiny JS lib for embedding (`<script>` tag) in arbitrary pages.
- `@epochix/sdk` — TypeScript SDK for non-Python trainers (JAX via JS bridges, Flux.jl wrappers, etc.).

### 25.3 Docker images

- `ghcr.io/epochix/server:<version>` — server-only.
- `ghcr.io/epochix/full:<version>` — server + Ollama + sample data.

### 25.4 Documentation site

- `docs.epochix.dev` — mkdocs-material.
- Deployed by CI on every tag.

### 25.5 Marketing & adoption

- Launch post on HN + r/MachineLearning.
- Demo video: a 90-second live training run with the dashboard side-by-side.
- Free hosted demo with public-only sample runs.

---

## 26. Open Decisions

These are unresolved choices that don't block v0.1 but should be discussed.

| # | Decision                              | Default for v0.1     | Notes |
|---|---------------------------------------|----------------------|-------|
| 1 | LLM fallback: Ollama vs OpenAI key    | Ollama, opt-in only  | Privacy by default |
| 2 | Hosted version: ship or wait          | Wait until v0.2      | Validate local UX first |
| 3 | Plugin system maturity                | Entry points only    | Versioned plugin API in v0.3 |
| 4 | Mobile dashboard layout               | Read-only, single column | Defer interactive scrubbing |
| 5 | i18n languages at launch              | en + fa + fr         | Maintainer team uses all three |
| 6 | TS frontend rewrite                   | No                   | Keep vanilla JS; revisit at 5k LOC |
| 7 | Auth in self-hosted team mode         | Basic auth + token   | OAuth at v0.3 |
| 8 | Telemetry on/off default              | OFF                  | Opt-in only, ever |

---

## 27. Implementation Surfaces

The same core engine is delivered through three distinct *surfaces* — each optimised for a different audience and friction point. They share parsers, story engine, and visual language; they differ only in how the user invokes them.

| Surface              | Audience                         | Friction        | Internet  | Backend |
|----------------------|----------------------------------|-----------------|-----------|---------|
| VS Code extension    | Engineers training locally       | One install     | optional  | Python sidecar (optional) |
| Claude artifact      | Anyone with a Claude account     | Paste a log     | required  | none — pure browser |
| Python library       | ML practitioners, integrations   | `pip install`   | optional  | optional (server) |

### 27.1 VS Code Extension

**Marketplace name:** `epochix.epochix` (publisher · extension)

#### 27.1.1 Goals

- A user opens VS Code, runs `python train.py` in the integrated terminal, and a panel **automatically** appears on the side with the live dashboard. No copy-paste, no second window, no separate server to launch.
- The status bar shows the current grade and phase emoji at a glance.
- Right-clicking a `.log` file in the explorer offers *"Open in Epochix"*.

#### 27.1.2 Two Operating Modes

The extension can run in **standalone mode** (pure TypeScript, no Python required) or **sidecar mode** (spawns the Python `epochix` server in the background for full feature parity).

| Capability                  | Standalone (TS only) | Sidecar (Python) |
|-----------------------------|----------------------|------------------|
| Built-in parsers            | ✓ (ported to TS)     | ✓                |
| Universal regex fallback    | ✓                    | ✓                |
| LLM fallback (Ollama)       | ✗                    | ✓                |
| Run history / DB            | ✗ (in-memory)        | ✓ (SQLite)       |
| HTML / PDF export           | ✗                    | ✓                |
| Plugin ecosystem            | ✗                    | ✓                |
| Install cost                | zero                 | requires Python ≥ 3.10 |

The extension auto-detects whether `epochix` is on `PATH`; if so, sidecar mode is enabled. Otherwise it falls back to standalone with a one-click banner: *"Install `pip install epochix` for advanced features."*

#### 27.1.3 File Structure

```
epochix-vscode/
├── package.json                       # manifest + contributes
├── README.md
├── CHANGELOG.md
├── LICENSE
├── tsconfig.json
├── esbuild.config.mjs
├── src/
│   ├── extension.ts                   # activate()/deactivate()
│   ├── commands/
│   │   ├── openDashboard.ts
│   │   ├── watchTerminal.ts
│   │   ├── openLogFile.ts
│   │   └── exportRun.ts
│   ├── webview/
│   │   ├── DashboardPanel.ts          # WebView manager
│   │   ├── webview.html.ts            # HTML shell
│   │   └── messages.ts                # typed protocol
│   ├── terminal/
│   │   ├── TerminalWatcher.ts         # listens to shellIntegration
│   │   └── TrainingDetector.ts        # heuristic: "is this an ML run?"
│   ├── sidecar/
│   │   ├── ServerManager.ts           # spawn / monitor / kill Python
│   │   ├── HealthCheck.ts
│   │   └── PortAllocator.ts
│   ├── parsers/                       # TS port of Python parsers
│   │   ├── base.ts
│   │   ├── pytorchLightning.ts
│   │   ├── keras.ts
│   │   ├── huggingface.ts
│   │   ├── yolo.ts
│   │   └── universal.ts
│   ├── story/                         # TS port of story_engine
│   │   ├── phases.ts
│   │   ├── grader.ts
│   │   ├── narrator.ts
│   │   └── templates/
│   ├── statusBar.ts                   # grade + phase pill
│   └── config.ts                      # vscode.workspace.getConfiguration
├── webview-dist/                      # output of `frontend/` build, vendored
│   ├── main.js
│   ├── main.css
│   └── assets/
└── media/
    └── icon.png
```

#### 27.1.4 `package.json` Manifest Highlights

```json
{
  "name": "epochix",
  "displayName": "Epochix",
  "publisher": "epochix",
  "version": "0.1.0",
  "engines": { "vscode": "^1.92.0" },
  "categories": ["Visualization", "Data Science", "Machine Learning"],
  "activationEvents": [
    "onCommand:epochix.openDashboard",
    "onCommand:epochix.watchTerminal",
    "onLanguage:python",
    "onView:epochixRuns",
    "workspaceContains:**/*.log"
  ],
  "main": "./dist/extension.js",
  "contributes": {
    "commands": [
      { "command": "epochix.openDashboard", "title": "Epochix: Open Dashboard" },
      { "command": "epochix.watchTerminal", "title": "Epochix: Watch Active Terminal" },
      { "command": "epochix.openLogFile",   "title": "Epochix: Open Log File…" },
      { "command": "epochix.exportRun",     "title": "Epochix: Export Current Run" },
      { "command": "epochix.compareRuns",   "title": "Epochix: Compare Two Runs" }
    ],
    "menus": {
      "explorer/context": [
        { "command": "epochix.openLogFile",
          "when": "resourceExtname == .log",
          "group": "navigation" }
      ],
      "editor/title": [
        { "command": "epochix.openLogFile",
          "when": "resourceExtname == .log",
          "group": "navigation" }
      ]
    },
    "views": {
      "explorer": [
        { "id": "epochixRuns", "name": "Epochix Runs" }
      ]
    },
    "configuration": {
      "title": "Epochix",
      "properties": {
        "epochix.autoWatchTerminal": {
          "type": "boolean", "default": true,
          "description": "Automatically open dashboard when training is detected in an integrated terminal."
        },
        "epochix.taskHint": {
          "type": "string",
          "enum": ["auto","classification","detection","regression","biometric","gaze","nlp"],
          "default": "auto"
        },
        "epochix.useSidecar": {
          "type": "string",
          "enum": ["auto","always","never"],
          "default": "auto",
          "description": "Use the Python `epochix` package if available."
        },
        "epochix.sidecarPath": {
          "type": "string", "default": "",
          "description": "Override path to the epochix executable."
        },
        "epochix.llmFallback": {
          "type": "boolean", "default": false,
          "description": "Enable Ollama LLM fallback parsing (requires Ollama running locally)."
        },
        "epochix.theme": {
          "type": "string", "enum": ["auto","light","dark"], "default": "auto"
        },
        "epochix.locale": {
          "type": "string", "enum": ["en","fa","fr"], "default": "en"
        }
      }
    },
    "keybindings": [
      { "command": "epochix.openDashboard",
        "key": "ctrl+alt+m", "mac": "cmd+alt+m" }
    ]
  }
}
```

#### 27.1.5 Activation & Terminal Watching

VS Code's **shell integration API** (`vscode.window.onDidWriteTerminalData` plus terminal shell integration) is the cleanest way to capture training output without asking the user to pipe anything.

```ts
// src/extension.ts (sketch)
import * as vscode from "vscode";
import { DashboardPanel } from "./webview/DashboardPanel";
import { TerminalWatcher } from "./terminal/TerminalWatcher";
import { ServerManager } from "./sidecar/ServerManager";

export async function activate(ctx: vscode.ExtensionContext) {
  const cfg = vscode.workspace.getConfiguration("epochix");
  const sidecar = await ServerManager.maybeStart(cfg);   // null if standalone

  const watcher = new TerminalWatcher(sidecar);
  ctx.subscriptions.push(watcher);

  if (cfg.get<boolean>("autoWatchTerminal")) {
    watcher.attachToActiveAutomatically();
  }

  ctx.subscriptions.push(
    vscode.commands.registerCommand("epochix.openDashboard",
      () => DashboardPanel.createOrShow(ctx.extensionUri, sidecar)),
    vscode.commands.registerCommand("epochix.watchTerminal",
      () => watcher.attachToActive()),
    vscode.commands.registerCommand("epochix.openLogFile",
      async (uri: vscode.Uri) => {
        const doc = uri ?? (await vscode.window.showOpenDialog({
          canSelectMany: false, filters: { Logs: ["log","txt","out"] }
        }))?.[0];
        if (doc) DashboardPanel.openLog(ctx.extensionUri, doc, sidecar);
      }),
  );
}
```

```ts
// src/terminal/TerminalWatcher.ts (sketch)
export class TerminalWatcher implements vscode.Disposable {
  private buffer = "";
  private disposable: vscode.Disposable;

  constructor(private sidecar: ServerManager | null) {
    this.disposable = vscode.window.onDidWriteTerminalData(e => {
      this.buffer += stripAnsi(e.data);
      // run training detector on the accumulated buffer's tail
      const detected = TrainingDetector.sniff(this.buffer.slice(-4096));
      if (detected && !DashboardPanel.current) {
        DashboardPanel.createOrShow(/*…*/);
      }
      DashboardPanel.current?.feedLines(this.buffer);
    });
  }
  dispose() { this.disposable.dispose(); }
}
```

#### 27.1.6 WebView Panel

The WebView loads the pre-built frontend bundle (vendored at `webview-dist/`). Communication uses VS Code's typed `postMessage` protocol:

```ts
// src/webview/messages.ts
export type ExtToWeb =
  | { type: "init"; theme: "light"|"dark"; locale: string; snapshot: StoryFrame[] }
  | { type: "frame"; frame: StoryFrame }
  | { type: "warning"; warning: Warning }
  | { type: "complete"; run: Run };

export type WebToExt =
  | { type: "ready" }
  | { type: "scrub"; seq: number }
  | { type: "export"; format: "html"|"pdf"|"md" }
  | { type: "openExternal"; url: string };
```

```ts
// src/webview/DashboardPanel.ts (sketch)
export class DashboardPanel {
  static current?: DashboardPanel;
  private constructor(private panel: vscode.WebviewPanel, /* … */) {
    panel.webview.html = renderHtml(/* … */);
    panel.webview.onDidReceiveMessage((m: WebToExt) => this.handle(m));
  }
  static createOrShow(extUri: vscode.Uri, sidecar: ServerManager | null) {
    if (DashboardPanel.current) {
      DashboardPanel.current.panel.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "epochix.dashboard", "Epochix",
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extUri, "webview-dist")] }
    );
    DashboardPanel.current = new DashboardPanel(panel, /*…*/);
  }
  feedLines(buffer: string) { /* parser → story → postMessage frame */ }
}
```

#### 27.1.7 Status Bar

```ts
const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
item.command = "epochix.openDashboard";
// updates on each new frame
item.text = `$(zap) ${frame.phaseEmoji} ${frame.grade}`;
item.tooltip = `Epochix · ${frame.narrative}`;
item.show();
```

#### 27.1.8 Sidecar Server Manager

```ts
// src/sidecar/ServerManager.ts (sketch)
export class ServerManager {
  static async maybeStart(cfg: vscode.WorkspaceConfiguration): Promise<ServerManager | null> {
    const mode = cfg.get<string>("useSidecar");
    if (mode === "never") return null;
    const bin = cfg.get<string>("sidecarPath") || "epochix";
    const found = await which(bin);
    if (!found && mode === "auto") return null;
    const port = await PortAllocator.findFree(7860);
    const proc = spawn(bin, ["serve", "--port", String(port), "--no-browser"], { detached: false });
    await HealthCheck.waitReady(`http://127.0.0.1:${port}/api/health`, 5000);
    return new ServerManager(proc, port);
  }
  dispose() { this.proc.kill(); }
}
```

#### 27.1.9 Distribution

- Published to VS Code Marketplace and Open VSX (for VSCodium / Cursor users).
- CI builds a `.vsix` per tag with vendored frontend.
- Bundle size budget: **< 5 MB** (.vsix). The Python sidecar is *not* bundled — users `pip install` separately.

#### 27.1.10 Cursor / Windsurf Compatibility

Cursor and Windsurf are VS Code forks and accept the same `.vsix`. No code changes required. Open VSX publication makes installation one click.

---

### 27.2 Claude Artifact

A Claude artifact is a single HTML/React file that runs entirely in the browser. There is no backend, no Python, no install. The user pastes their training log into a textarea and the dashboard renders.

This surface is the **lowest-friction proof of concept** — useful for demos, screenshots, and for non-technical stakeholders who don't want to install anything.

#### 27.2.1 Goals

- Zero install. Open Claude → paste log → see dashboard.
- Drag-and-drop a `.log` file from the desktop also works.
- Pure client-side: parsers and story engine run in the browser.
- Optional LLM fallback uses Claude's own API (Section 27.2.5).

#### 27.2.2 Constraints (per the artifact runtime)

These are hard limits of the artifact environment and shape the design:

- **No browser storage.** `localStorage` / `sessionStorage` are not available. All run data lives in React state for the session only — it's gone on tab close. The user can download a `report.html` to preserve their work.
- **No external `<link>` or `<script>` fetches** beyond the whitelisted CDN imports. Fonts must be system fonts or inlined.
- **Tailwind utilities only** (no `@apply`, no PostCSS pipeline).
- **Allowed libraries** (import paths from the artifact spec): `recharts`, `d3`, `three`, `lodash`, `mathjs`, `lucide-react`, `papaparse`, `tone`, `chart.js`, `shadcn/ui`. (No `framer-motion` — use CSS keyframes or `react-spring` shims via inline implementations.)
- **No file system writes.** Exports happen via `Blob` + a `<a download>` click.

#### 27.2.3 Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    Claude Artifact (single file)                │
│                                                                 │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │  Input zone     │    │   Display panels                 │   │
│  │  ┌───────────┐  │    │   ┌─────────┐  ┌──────────┐      │   │
│  │  │ Paste log │──┼───►│   │  Brain  │  │ Timeline │      │   │
│  │  │ Drop file │  │    │   │ (three) │  │  (DOM)   │      │   │
│  │  └───────────┘  │    │   └─────────┘  └──────────┘      │   │
│  └────────┬────────┘    │   ┌─────────┐  ┌──────────┐      │   │
│           │             │   │ Liquid  │  │  Radar   │      │   │
│           ▼             │   │  (SVG)  │  │ (recharts)│      │   │
│  ┌─────────────────┐    │   └─────────┘  └──────────┘      │   │
│  │  Pipeline (JS)  │    │   ┌──────────────────────────┐   │   │
│  │ ┌─────────────┐ │    │   │  Engineer charts         │   │   │
│  │ │ Detect fmt  │ │    │   │  (chart.js / recharts)   │   │   │
│  │ │ Parse       │─┼───►│   └──────────────────────────┘   │   │
│  │ │ Normalize   │ │    │   ┌──────────────────────────┐   │   │
│  │ │ Story       │ │    │   │  Scrubber (range input)  │   │   │
│  │ └─────────────┘ │    │   └──────────────────────────┘   │   │
│  └─────────────────┘    └──────────────────────────────────┘   │
│           │                                                     │
│           │  (Optional) unknown lines                           │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Claude API call (fetch /v1/messages)                   │   │
│  │  → asks for JSON extraction of metric key/values        │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

#### 27.2.4 Single-File React Skeleton

```jsx
// epochix.artifact.jsx
import { useState, useMemo, useRef, useEffect } from "react";
import { Upload, Download, Brain, Zap } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import * as THREE from "three";

// ============================================================
//  1.  PARSERS (ported from Python)
// ============================================================
const parsers = {
  pytorchLightning: {
    sniff: (lines) => lines.some(l => /Epoch \d+\/\d+:.*\|.*loss=/.test(l)) ? 0.95 : 0,
    parse: (line) => {
      const m = line.match(/Epoch (\d+)\/(\d+).*?loss=([\d.]+).*?acc(?:uracy)?=([\d.]+)/);
      return m ? [
        { epoch: +m[1], key: "train_loss", value: +m[3] },
        { epoch: +m[1], key: "accuracy",   value: +m[4] },
      ] : [];
    }
  },
  keras: { /* … */ },
  huggingface: { /* … */ },
  yolo: { /* … */ },
  universal: {
    sniff: () => 0.1,
    parse: (line) => {
      const out = [];
      const re = /(\w+)\s*[=:]\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;
      let m; while ((m = re.exec(line))) out.push({ key: m[1], value: +m[2] });
      return out;
    }
  }
};

function detectParser(lines) {
  return Object.entries(parsers)
    .map(([name, p]) => ({ name, score: p.sniff(lines) }))
    .sort((a, b) => b.score - a.score)[0];
}

// ============================================================
//  2.  STORY ENGINE (ported)
// ============================================================
const phaseFor = (progress, rel) => {
  if (progress < 0.10) return { id: "awakening", emoji: "🌱", color: "#f59e0b" };
  if (progress < 0.40 || rel < 0.40) return { id: "learning", emoji: "📚", color: "#3b82f6" };
  if (progress < 0.70 || rel < 0.75) return { id: "understanding", emoji: "💡", color: "#8b5cf6" };
  if (progress < 0.95 || rel < 0.95) return { id: "mastering", emoji: "⚡", color: "#10b981" };
  return { id: "polishing", emoji: "✨", color: "#14b8a6" };
};

const gradeFor = (v, thresholds) => {
  for (const [g, t] of thresholds) if (v >= t) return g;
  return "F";
};

const NARRATIVES = {
  awakening:     "The model is seeing its first examples. Everything looks the same to it.",
  learning:      "Patterns are starting to click. The easy cases are clicking into place.",
  understanding: "Most of the answers are right. The hard edge cases remain.",
  mastering:     "Only the trickiest cases still trip it up. Confidence is high.",
  polishing:     "Last refinements. The model is locking in what it already knows.",
};

// ============================================================
//  3.  OPTIONAL LLM FALLBACK (Claude API in artifacts)
// ============================================================
async function llmExtract(unknownLines) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{
        role: "user",
        content:
          "Extract training metrics as JSON: " +
          "{epoch:int, key:str, value:float}[]. " +
          "Reply with ONLY the JSON array, no prose. Lines:\n" +
          unknownLines.slice(0, 30).join("\n")
      }]
    })
  });
  const data = await res.json();
  const text = data.content.filter(b => b.type === "text").map(b => b.text).join("");
  try { return JSON.parse(text.replace(/```json|```/g, "").trim()); } catch { return []; }
}

// ============================================================
//  4.  MAIN COMPONENT
// ============================================================
export default function EpochixArtifact() {
  const [logText, setLogText] = useState("");
  const [frames, setFrames] = useState([]);
  const [currentSeq, setCurrentSeq] = useState(0);

  // Re-parse whenever the log changes
  useEffect(() => {
    if (!logText.trim()) { setFrames([]); return; }
    const lines = logText.split("\n");
    const chosen = detectParser(lines.slice(0, 50));
    const parser = parsers[chosen.name];
    const metrics = [];
    for (const line of lines) {
      for (const m of parser.parse(line)) metrics.push(m);
    }
    // Build StoryFrames from metrics …
    setFrames(buildFrames(metrics));
  }, [logText]);

  const current = frames[currentSeq] || frames.at(-1);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6">
      {/* Input zone */}
      <textarea
        className="w-full h-32 p-3 rounded-lg border bg-white dark:bg-slate-800"
        placeholder="Paste your training log here…"
        value={logText}
        onChange={(e) => setLogText(e.target.value)}
      />
      <DropZone onDrop={setLogText} />

      {/* Display */}
      {current && (
        <>
          <HeroPanel frame={current} />
          <ChartPanel frames={frames} />
          <TimelinePanel frames={frames} onScrub={setCurrentSeq} />
          <ExportButton frames={frames} />
        </>
      )}
    </div>
  );
}
```

#### 27.2.5 LLM Fallback Inside an Artifact

The artifact environment lets a single HTML page call `https://api.anthropic.com/v1/messages` without a user-supplied key — the runtime injects authentication. This is the same mechanism that powers "Claude in Claude" / Claudeception artifacts.

Use it sparingly: a single call to extract metrics from up to 30 unknown lines is good UX, but calling per-line is wasteful and slow.

#### 27.2.6 Export from Artifact

Because there's no file system, export uses `Blob`:

```js
function downloadHtml(html) {
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"),
    { href: url, download: "epochix-report.html" });
  a.click();
  URL.revokeObjectURL(url);
}
```

The exported HTML is a smaller version of the live artifact (no React, just inlined parsed data + read-only viewer). Target size: **< 500 KB** for the artifact-side export (versus < 2 MB for the full Python-exported version).

#### 27.2.7 Limitations vs. Full Library

| Feature                  | Artifact | Library |
|--------------------------|----------|---------|
| Drag-and-drop log file   | ✓        | ✓ (CLI) |
| Paste log directly       | ✓        | ✗       |
| Live streaming           | ✗        | ✓       |
| Run history (multi-run)  | ✗        | ✓       |
| PDF export               | ✗        | ✓       |
| Plugin parsers           | ✗        | ✓       |
| Works offline            | ✗        | ✓       |
| Cross-session persistence| ✗        | ✓       |
| LLM fallback             | ✓ (Claude API) | ✓ (Ollama / OpenAI) |
| Install cost             | none     | `pip install` |

#### 27.2.8 Use as Marketing Funnel

The artifact is *also* the project's best onboarding tool. After a user pastes a log and sees the dashboard, the artifact shows a one-line banner: *"Like this? `pip install epochix` for live streaming, run history, and exports."*

---

### 27.3 Python Library (Deep Dive)

This subsection expands §15.2 with the full library design — public surface, packaging, type hints, versioning, and integration patterns.

#### 27.3.1 Public API Surface

Everything a user interacts with is re-exported from `epochix/__init__.py`. Anything not in this list is implementation detail and may change without notice.

```python
# epochix/__init__.py
from .sdk.parse import parse, parse_string
from .sdk.live_reporter import LiveReporter
from .sdk.compare import compare
from .sdk.visualize import visualize, serve
from .sdk.export import export
from .models import Run, MetricEvent, StoryFrame, Milestone, Warning
from .enums import Phase, Grade, TaskType
from .parsers import register_parser, BaseParser
from .integrations.lightning import StoryCallback as LightningCallback
from .integrations.hf import StoryCallback as HuggingFaceCallback

__all__ = [
    "parse", "parse_string", "LiveReporter", "compare",
    "visualize", "serve", "export",
    "Run", "MetricEvent", "StoryFrame", "Milestone", "Warning",
    "Phase", "Grade", "TaskType",
    "register_parser", "BaseParser",
    "LightningCallback", "HuggingFaceCallback",
]
__version__ = "0.1.0"
```

#### 27.3.2 Five Integration Patterns

Each pattern fits a different user workflow. None require changes to the existing training code beyond a single import.

**Pattern 1 — Zero-code (parse a finished log):**

```python
import epochix as ms
run = ms.parse("train.log")
ms.visualize(run)                  # opens browser
```

**Pattern 2 — One-line live (pipe stdout):**

```bash
python train.py 2>&1 | epochix --live
```

**Pattern 3 — Explicit reporter (most control):**

```python
from epochix import LiveReporter

reporter = LiveReporter(
    task="gaze",
    primary_metric="mae",
    name="gazeformer_v7",
    config={"lr": 3e-4, "batch_size": 64},   # captured as run metadata
)
with reporter:                                # auto-finish on exit/exception
    for ep in range(100):
        loss, mae = train_epoch()
        reporter.log(epoch=ep, train_loss=loss, mae=mae)
```

**Pattern 4 — Framework callback (PyTorch Lightning):**

```python
import pytorch_lightning as pl
from epochix import LightningCallback

trainer = pl.Trainer(
    max_epochs=100,
    callbacks=[LightningCallback(task="biometric", open_browser=True)],
)
trainer.fit(model, dm)
```

**Pattern 5 — Decorator (research scripts):**

```python
from epochix import story

@story(task="classification", primary_metric="val_acc")
def train_epoch(model, loader, epoch):
    ...
    return {"train_loss": loss, "val_acc": acc, "epoch": epoch}

for ep in range(100):
    train_epoch(model, loader, ep)            # auto-logged
```

#### 27.3.3 `LiveReporter` API

```python
class LiveReporter:
    def __init__(
        self,
        *,
        task: TaskType | str | None = None,
        primary_metric: str | None = None,
        name: str | None = None,
        config: dict | None = None,
        port: int = 7860,
        host: str = "127.0.0.1",
        open_browser: bool = True,
        db_path: str | Path | None = None,
        scrub_secrets: bool = False,
        llm_fallback: bool = False,
    ) -> None: ...

    def log(self, **metrics: float | int) -> None: ...
    def log_raw(self, line: str) -> None: ...           # for parser-style ingestion
    def add_warning(self, kind: str, message: str) -> None: ...
    def add_milestone(self, kind: str, message: str, value: float | None = None) -> None: ...
    def finish(self, status: str = "complete") -> Run: ...
    def export(self, format: Literal["html","pdf","md","json"], path: str | Path) -> Path: ...
    def link(self) -> str: ...                          # http://127.0.0.1:7860/v/<id>
    def __enter__(self) -> LiveReporter: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
```

#### 27.3.4 `parse()` API

```python
def parse(
    source: str | Path | TextIO,
    *,
    task: TaskType | str | None = None,
    parser: str | None = None,                 # force a specific parser
    primary_metric: str | None = None,
    name: str | None = None,
    llm_fallback: bool = False,
) -> Run: ...

def parse_string(text: str, **kwargs) -> Run: ...
```

#### 27.3.5 Packaging (`pyproject.toml`)

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "epochix"
version = "0.1.0"
description = "Visual storytelling for deep learning training runs."
authors = [{ name = "Epochix Team" }]
license = "Apache-2.0"
readme = "README.md"
requires-python = ">=3.10"
keywords = ["machine-learning","training","visualization","mlops"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Science/Research",
  "License :: OSI Approved :: Apache Software License",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
dependencies = [
  "pydantic>=2.7",
  "pydantic-settings>=2.4",
  "fastapi>=0.116",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "typer>=0.12",
  "structlog>=24.1",
  "python-ulid>=2.7",
  "anyio>=4.4",
]

[project.optional-dependencies]
pdf       = ["weasyprint>=62"]
lightning = ["pytorch-lightning>=2.3"]
hf        = ["transformers>=4.40"]
llm       = ["httpx>=0.27"]                   # for Ollama / OpenAI calls
postgres  = ["asyncpg>=0.30"]
redis     = ["redis>=5.0"]
all       = ["epochix[pdf,lightning,hf,llm]"]

dev       = ["pytest>=8", "pytest-asyncio", "pytest-benchmark",
             "hypothesis>=6.108", "ruff", "mypy", "playwright",
             "schemathesis", "pre-commit"]

[project.scripts]
epochix = "epochix.cli:app"

[project.entry-points."epochix.parsers"]
pytorch_lightning   = "epochix.parsers.pytorch_lightning:PLParser"
keras_tensorflow    = "epochix.parsers.keras_tensorflow:KerasParser"
huggingface         = "epochix.parsers.huggingface:HFParser"
ultralytics_yolo    = "epochix.parsers.ultralytics_yolo:YOLOParser"
fastai              = "epochix.parsers.fastai:FastAIParser"
universal           = "epochix.parsers.universal:UniversalParser"

[tool.hatch.build.targets.wheel]
packages = ["src/epochix"]
[tool.hatch.build.targets.wheel.force-include]
"frontend/dist" = "epochix/_frontend/dist"
```

#### 27.3.6 Type Safety

- All public functions and methods have **full type hints**.
- `py.typed` marker file ships with the wheel (PEP 561) so downstream users get inline type-checking.
- mypy is run in `--strict` mode in CI for `src/epochix/`. Examples and tests are not strict-checked but still type-annotated.

#### 27.3.7 Versioning Policy

- SemVer: **MAJOR.MINOR.PATCH**.
- Public API is everything in `epochix/__init__.py`'s `__all__` plus the on-disk SQLite schema and the WS/SSE message envelopes.
- Breaking changes to the public API increment MAJOR.
- New parsers, new task types, new visualizations are MINOR.
- Bug fixes and docs are PATCH.
- Pre-1.0 (the `0.x` line) reserves the right to break minor APIs in MINOR bumps, but the *plugin protocol* and *data schemas* follow stricter rules from day one.

#### 27.3.8 Cross-Platform Considerations

| Concern                  | Approach                                                        |
|--------------------------|-----------------------------------------------------------------|
| Stdin on Windows         | `asyncio.StreamReader` + msvcrt loop fallback                   |
| `tail -f` on Windows     | Polling fallback when `inotify`/`kqueue` unavailable            |
| Browser auto-open        | `webbrowser.open` (stdlib, cross-platform)                      |
| Path separators          | `pathlib.Path` everywhere; never string concat                  |
| SQLite WAL on network FS | Detect and warn; fall back to `journal_mode=DELETE`             |
| Terminal colour codes    | Strip ANSI before parsing                                       |
| Encoding                 | Read with `errors="replace"`; never crash on bad bytes          |

#### 27.3.9 Bundled Frontend

The wheel includes a pre-built frontend bundle at `epochix/_frontend/dist/`. Users do **not** need Node or npm to install or use the package. The frontend is rebuilt and re-vendored once per release by CI.

#### 27.3.10 Documentation Conventions

- MkDocs-material for the docs site.
- Every public function in `__all__` has a docstring with at least one **runnable** example.
- The README has three things and only three things: a 20-second video, three commands to copy-paste, and a link to the docs.
- API reference is auto-generated by `mkdocstrings` from docstrings — never hand-written.

#### 27.3.11 Quality Gates Before Each Release

1. `pytest -q` green on Linux, macOS, Windows × Python 3.10/3.11/3.12.
2. `ruff check` clean.
3. `mypy --strict src/epochix` clean.
4. `playwright test` green (E2E across the 6 fixture logs).
5. Bundle size: wheel < 8 MB, exported HTML < 2 MB.
6. `pip install` in a clean venv → `epochix demo/pytorch_lightning.log` opens the dashboard.
7. `CHANGELOG.md` updated.

---

### 27.4 How the Three Surfaces Share Code

A schematic of code reuse across the three surfaces, so contributors know where to land a fix:

```
                       ┌──────────────────────────┐
                       │  Core engine (Python)    │
                       │  parsers / story / store │
                       └──────────┬───────────────┘
                                  │
                  ┌───────────────┼────────────────┐
                  ▼               ▼                ▼
        ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
        │ Library (PyPI)   │  │ VS Code ext  │  │ Claude artifact  │
        │                  │  │  (sidecar)   │  │ (TS port)        │
        │ Native Python    │  │  Spawns the  │  │ Pure browser;    │
        │ users; CLI/SDK.  │  │  Python lib  │  │ subset of parsers│
        │                  │  │  as subproc; │  │ & story engine   │
        │                  │  │  TS port for │  │ ported to JS.    │
        │                  │  │  standalone. │  │                  │
        └──────────────────┘  └──────────────┘  └──────────────────┘
```

- **Single source of truth for parsers and story logic: Python.** TS ports are generated semi-automatically with a tool in `scripts/python-to-ts-parser.py` to reduce drift.
- **Single source of truth for visuals: the `frontend/` directory.** Both the library and the VS Code extension vendor the same built bundle. The Claude artifact reimplements a subset because it can't load the bundle.
- **Schema is shared via JSON Schema export.** `epochix dump-schema > schema.json` produces a file consumed by both the TS parser ports and the artifact's type definitions.

---

## Appendix A — Sample Log Signatures

These are the regex anchors each structured parser uses for sniffing. Stored here for review and future contribution.

### A.1 PyTorch Lightning

```
Epoch (\d+)/(\d+):\s+\d+%\|.*\|\s+(\d+)/\d+\s+\[.*\]\s+(.*?)$
```
Plus key-value extraction from the metric tail: `loss=0.432 acc=0.867`.

### A.2 Keras / TF

```
Epoch (\d+)/(\d+)
\d+/\d+ \[=+>?\.*\] - .* - (loss|val_loss|accuracy|val_accuracy): ([\d.eE+-]+)
```

### A.3 HuggingFace Trainer

```
^\{'loss': ([\d.eE+-]+), 'learning_rate': ([\d.eE+-]+), 'epoch': ([\d.eE+-]+).*\}$
```

### A.4 Ultralytics YOLO

```
^\s*(\d+)/(\d+)\s+([\d.]+G)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\d+\s*$
                       ^GPU mem    ^box     ^cls    ^dfl
```
Plus the validation row: `all  N  M  P  R  mAP50  mAP50-95`.

### A.5 FastAI

```
^\s*\d+\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d:]+)\s*$
            train_loss     valid_loss    metric         time
```

### A.6 Universal fallback

Three patterns tried in order, per line:

```
1. (\w+)\s*=\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)   # key=value
2. (\w+)\s*:\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)   # key: value
3. \{[^{}]*\}                                            # JSON-ish dict
```

---

## Appendix B — Metaphor Library

Excerpt from the default English templates. Each task × phase combination has 3–5 variants chosen randomly with a deterministic seed (the `run_id`) so the same run always tells the same story.

### Classification

| Phase           | Example narrative                                                             |
|-----------------|-------------------------------------------------------------------------------|
| Awakening       | "The model is seeing its first examples. Everything looks the same to it."   |
| Learning        | "Patterns are starting to click. The model recognises the easy cases now."   |
| Understanding   | "Most of the answers are right. The hard edge cases remain."                  |
| Mastering       | "Only the trickiest cases still trip it up. Confidence is high."              |
| Polishing       | "Last refinements. The model is locking in what it already knows."            |

### Biometric (EER, lower = better)

| Phase           | Example narrative                                                              |
|-----------------|--------------------------------------------------------------------------------|
| Awakening       | "Learning what makes each person's fingerprint unique."                        |
| Learning        | "Ridge patterns, minutiae, whorls — building an internal vocabulary."          |
| Understanding   | "Distinguishing similar fingers is no longer a coin flip."                     |
| Mastering       | "Twin patterns and damaged scans — the hardest cases — are being handled."     |
| Polishing       | "Final tightening. The error rate is now in the 'production-grade' band."     |

### Gaze / Regression (MAE in degrees or cm)

| Phase           | Example narrative                                                              |
|-----------------|--------------------------------------------------------------------------------|
| Awakening       | "The model is still pointing in the wrong direction most of the time."         |
| Learning        | "It can roughly tell where on the screen you're looking."                      |
| Understanding   | "Predictions land within a few centimetres of the actual gaze point."          |
| Mastering       | "Sub-centimetre accuracy on most users."                                       |
| Polishing       | "Squeezing the last fraction of a degree of error."                            |

### Detection (mAP)

| Phase           | Example narrative                                                              |
|-----------------|--------------------------------------------------------------------------------|
| Awakening       | "The model can tell *something* is there, but not what or exactly where."     |
| Learning        | "Most large, obvious objects are now being found."                             |
| Understanding   | "Smaller and partially occluded objects are getting picked up."                |
| Mastering       | "Even under tight overlap rules, the model is finding most of the targets."    |
| Polishing       | "Diminishing returns — fine-tuning the bounding boxes."                        |

### NLP / Language Model (perplexity)

| Phase           | Example narrative                                                              |
|-----------------|--------------------------------------------------------------------------------|
| Awakening       | "The model is overwhelmed by language — every sentence is surprising."         |
| Learning        | "Common phrases are no longer surprising. Rare ones still are."                |
| Understanding   | "Most well-formed text is predictable. Style and tone are next."               |
| Mastering       | "Style, tone, and structure are well-modeled."                                 |
| Polishing       | "Refining edge cases — code, math, multilingual passages."                     |

---

**End of Architecture Specification — v1.0**

*Maintainers: Epochix Team. Pull requests welcome.*
