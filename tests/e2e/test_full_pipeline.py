"""End-to-end "fresh-install" pipeline tests.

These walk the exact path a brand-new user takes:

    pip install epochix
    epochix <log>               # or: epochix demo

For every model family the parsers understand (PyTorch Lightning, Keras,
HuggingFace, YOLOv8, seq2seq+attention, biometric/EER, gaze/MAE) we feed the
real log through the same async pipeline the CLI uses, then assert:

* the run was created and persisted,
* the task type was auto-detected (or matches an explicit override),
* a story-frame trajectory was produced with valid phase/grade per frame,
* the metric series contains the canonical keys the dashboard needs,
* the architecture was extracted where the log includes a model summary,
* the HTTP API the frontend calls (/api/runs · /api/snapshot · /api/metrics ·
  /api/export/{id}/json) returns shape-correct, non-empty payloads.

A long-trajectory test additionally synthesises a 50-epoch PL-style log so
that phase progression (Awakening → … → Polishing) can be observed against a
realistic loss/accuracy curve — covers the "epoch 1 → 50" expectation that
short demos can't satisfy on their own.

A fresh-install smoke test invokes the bundled `epochix demo` command
programmatically to verify the zero-input on-boarding path that ships in the
wheel.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epochix import parse
from epochix.config import Settings
from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.sdk.parse import parse_string
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"

# (filename, expected_task, required_canonical_keys, min_frames, architecture_expected)
#
# - `expected_task` of `None` means "any valid TaskType — we just verify task
#   detection picked something" (the universal/HF demos auto-detect to
#   whichever family the canonical keys point at).
# - `min_frames` is conservative — yolov8.log only logs 2 epochs.
# - `architecture_expected` is True for logs that include a model summary.
MODEL_MATRIX = [
    ("pytorch_lightning.log", TaskType.CLASSIFICATION, {"val_loss", "accuracy"}, 4, True),
    ("keras_image_classifier.log", TaskType.CLASSIFICATION, {"val_accuracy"}, 3, True),
    ("huggingface_bert.log", None, {"val_loss"}, 3, False),
    ("yolov8_detection.log", TaskType.DETECTION, {"mAP50"}, 1, True),
    ("seq2seq_attention.log", None, {"val_loss"}, 3, True),
    # fingerprint log uses "Epoch N\n  key=val" (metrics on the next line);
    # the universal parser pulls the EER values out, but the line-by-line
    # epoch association is conservative, so only the final epoch reliably
    # emits a frame. The test still verifies the EER series is captured.
    ("fingerprint_matching.log", TaskType.BIOMETRIC, {"EER"}, 1, False),
    ("gaze_estimation.log", TaskType.GAZE, {"MAE"}, 3, False),
]


# ── shared helpers ───────────────────────────────────────────────────────────


def _read_back(
    db_path: str,
    run_id: str,
) -> tuple[RunStore, Run | None, list[StoryFrame], list[MetricEvent]]:
    """Open the persisted DB and pull the data the frontend would receive."""
    store = RunStore(db_path=db_path)
    run = store.get_run(run_id)
    frames = store.get_story_frames(run_id)
    metrics = store.get_metric_events(run_id)
    return store, run, frames, metrics


def _generate_pl_log(epochs: int = 50) -> str:
    """Realistic PyTorch-Lightning-style log with smooth loss/acc curves.

    Loss decays exponentially from ~2.3 → ~0.2; accuracy rises sigmoidally
    from ~0.10 → ~0.92. Trains the long-trajectory + phase-progression tests.
    """
    lines = [
        "GPU available: True (cuda), used: True",
        "",
        "  | Name    | Type       | Params",
        "-----------------------------------",
        "0 | encoder | ResNet50   | 23.5 M",
        "1 | head    | Linear     | 2.1 K",
        "-----------------------------------",
        "23.5 M    Trainable params",
        "0         Non-trainable params",
        "23.5 M    Total params",
        "",
    ]
    for i in range(1, epochs + 1):
        # exponential decay for loss, logistic for accuracy
        loss = 0.2 + 2.1 * math.exp(-i / 8.0)
        acc = 0.1 + 0.82 / (1.0 + math.exp(-(i - epochs / 3) / 5.0))
        val_loss = loss * 1.04 + 0.02
        val_acc = acc - 0.015
        lines.append(
            f"Epoch {i}/{epochs}: 100%|████| 250/250 [00:13<00:00, "
            f"loss={loss:.3f}, acc={acc:.3f}, val_loss={val_loss:.3f}, "
            f"val_acc={val_acc:.3f}]"
        )
    return "\n".join(lines) + "\n"


# ── 1. The matrix: every model family, real demo logs ────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected_task", "required_keys", "min_frames", "arch_expected"),
    MODEL_MATRIX,
    ids=[m[0].removesuffix(".log") for m in MODEL_MATRIX],
)
def test_demo_log_produces_real_dashboard_data(
    filename: str,
    expected_task: TaskType | None,
    required_keys: set[str],
    min_frames: int,
    arch_expected: bool,
    tmp_path: Path,
) -> None:
    """Each bundled demo must run end-to-end and yield real dashboard content."""
    log_path = DEMO_DIR / filename
    assert log_path.is_file(), f"missing demo log: {filename}"

    db_path = str(tmp_path / "runs.db")
    run = parse(
        log_path,
        db=db_path,
        task=expected_task.value if expected_task else None,
        run_name=f"e2e/{filename}",
    )

    # --- Run-level sanity --------------------------------------------------
    assert run.id, "parse() must return a Run with an id"
    assert run.task_type in TaskType, "task_type must be a valid TaskType"
    if expected_task is not None:
        assert run.task_type == expected_task, (
            f"{filename}: expected {expected_task}, got {run.task_type}"
        )
    assert run.final_grade in Grade, "final grade must be a valid Grade letter"
    assert run.story_summary, "every run must carry a human-readable summary"

    # --- Persisted frames + metrics (what the dashboard fetches) ------------
    _, persisted_run, frames, metrics = _read_back(db_path, run.id)
    assert persisted_run is not None
    assert len(frames) >= min_frames, f"{filename}: only {len(frames)} frames (< {min_frames})"
    assert len(metrics) > 0, f"{filename}: pipeline stored zero metric events"

    seen_keys = {m.canonical_key for m in metrics}
    missing = required_keys - seen_keys
    assert not missing, f"{filename}: missing canonical keys {missing} (saw {seen_keys})"

    # --- Architecture detection --------------------------------------------
    arch = (persisted_run.config or {}).get("architecture") if persisted_run else None
    if arch_expected:
        assert arch, f"{filename}: expected detected architecture, got {arch!r}"
        assert isinstance(arch, list) and len(arch) > 0
        # Every layer should carry the schema the BrainCanvas relies on.
        for layer in arch:
            assert {"name", "layer_type", "visual_type"} <= set(layer.keys())

    # --- Every frame is renderable -----------------------------------------
    for f in frames:
        assert f.phase in Phase
        assert f.grade in Grade
        assert isinstance(f.narrative, str) and f.narrative.strip(), (
            "every frame must produce a non-empty narrative — the dashboard renders it verbatim"
        )
        assert f.primary_metric_value is not None
        assert math.isfinite(f.primary_metric_value), "NaN/inf must never reach the store"
        # `confidence` is now the (honest) training-advancement scalar — must
        # stay clamped to [0,1] regardless of upstream metric scale.
        assert 0.0 <= f.confidence <= 1.0


# ── 2. Long-trajectory + phase progression (the "epoch 1 → 50" coverage) ─────


def test_50_epoch_run_progresses_through_phases(tmp_path: Path) -> None:
    """A realistic 50-epoch trajectory must walk from Awakening to Polishing.

    Short demos can't exercise late-phase behaviour. This synthesises a smooth
    loss/accuracy curve covering 50 epochs and asserts the story engine moves
    the model through multiple phases on the way to the optimum.
    """
    log_text = _generate_pl_log(epochs=50)
    db_path = str(tmp_path / "long.db")

    run = parse_string(
        log_text,
        db=db_path,
        run_name="long-50-epochs",
        task=TaskType.CLASSIFICATION.value,
    )
    _, _, frames, _ = _read_back(db_path, run.id)

    assert len(frames) >= 25, f"long trajectory should produce many frames; got {len(frames)}"

    phases_seen = [f.phase for f in frames]
    distinct_phases = set(phases_seen)
    assert Phase.AWAKENING in distinct_phases or Phase.LEARNING in distinct_phases, (
        "early frames must be in an early phase"
    )
    # By the end of a 50-epoch run with rising accuracy and falling loss, the
    # engine should have left the early phases entirely.
    assert phases_seen[-1] in {Phase.MASTERING, Phase.POLISHING, Phase.UNDERSTANDING}, (
        f"last phase was {phases_seen[-1]} — long runs should reach late phases"
    )
    assert len(distinct_phases) >= 2, (
        f"expected multiple phases over 50 epochs, only saw {distinct_phases}"
    )

    # Advancement should grow monotonically-ish across the run (allow tiny
    # noise via a strict-enough endpoint comparison instead of every-frame
    # monotonicity).
    assert frames[0].progress < frames[-1].progress, (
        f"progress did not grow: {frames[0].progress} → {frames[-1].progress}"
    )
    # And the primary metric (accuracy) really did improve.
    assert frames[-1].primary_metric_value > frames[0].primary_metric_value


# ── 3. HTTP API — what a freshly-opened dashboard tab actually fetches ───────


def test_http_api_returns_renderable_dashboard_payload(tmp_path: Path) -> None:
    """Pretend a user opened http://127.0.0.1:7860/v/<run_id> and confirm every
    endpoint the frontend calls returns real, frontend-shaped data."""
    # First ingest a run; persist it to a real on-disk SQLite the server reads.
    db_path = str(tmp_path / "ui.db")
    run = parse(
        DEMO_DIR / "pytorch_lightning.log",
        db=db_path,
        run_name="ui-smoke",
    )

    app = create_app(settings=Settings(db=db_path, expose_docs=True))
    with TestClient(app) as client:
        # GET /api/runs — landing page list
        r = client.get("/api/runs")
        assert r.status_code == 200, r.text
        listing = r.json()
        assert listing["total"] >= 1
        ids = {x["id"] for x in listing["runs"]}
        assert run.id in ids

        # GET /api/snapshot/{id} — initial dashboard fetch
        r = client.get(f"/api/snapshot/{run.id}")
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["total_frames"] >= 4
        first = snap["frames"][0]
        assert {"phase", "grade", "primary_metric_value", "narrative", "confidence"} <= set(first)
        # Architecture is the input the BrainCanvas needs to render layer slabs.
        arch = (snap["run"] or {}).get("config", {}).get("architecture")
        assert arch and isinstance(arch, list)

        # GET /api/metrics/{id} — engineer-panel curve source
        r = client.get(f"/api/metrics/{run.id}")
        assert r.status_code == 200, r.text
        metrics = r.json()
        assert metrics["total_events"] > 0
        # The dashboard wants both loss + an accuracy-like metric.
        keys = {e["canonical_key"] for e in metrics["events"]}
        assert any(k in keys for k in {"accuracy", "val_accuracy"})
        assert any(k in keys for k in {"train_loss", "val_loss"})

        # GET /api/export/{id}/json — “share this run” button
        r = client.get(f"/api/export/{run.id}/json")
        assert r.status_code == 200
        export = r.json()
        assert export["run"]["id"] == run.id
        assert len(export["frames"]) >= 4
        assert len(export["events"]) > 0


# ── 4. Compare view — two runs side-by-side ──────────────────────────────────


def test_compare_endpoint_returns_two_runs(tmp_path: Path) -> None:
    """The /compare view loads N runs at once; verify multi-run aggregation."""
    db_path = str(tmp_path / "cmp.db")
    a = parse(DEMO_DIR / "keras_image_classifier.log", db=db_path, run_name="A")
    b = parse(DEMO_DIR / "pytorch_lightning.log", db=db_path, run_name="B")

    app = create_app(settings=Settings(db=db_path))
    with TestClient(app) as client:
        r = client.get(f"/api/compare?run_ids={a.id},{b.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        ids = {entry["run"]["id"] for entry in body["runs"]}
        assert ids == {a.id, b.id}
        for entry in body["runs"]:
            assert len(entry["frames"]) > 0
            assert len(entry["metrics"]) > 0


# ── 5. Fresh-install smoke test: the bundled `epochix demo` command ──────


def test_bundled_demo_command_runs_without_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user with nothing but `pip install epochix` should be able to type
    `epochix demo` and see real data. Programmatically exercise that path
    against each of the three bundled demos so a regression in packaging,
    aliasing or the run plumbing is caught before release.
    """
    from epochix.cli import cmd_demo

    # Redirect the store to a temp DB so we don't write to the user's home.
    monkeypatch.setenv("EPOCHIX_DB", str(tmp_path / "demo.db"))

    for alias in ("seq2seq", "yolov8", "keras"):
        # `cmd_demo` reuses cmd_run under the hood; --headless prevents the
        # browser open. Asserting no exception is the smoke check.
        cmd_demo(name=alias, port=0, headless=True, log_level="WARNING")

    # Verify the runs actually landed in the DB the env var pointed at.
    store = RunStore(db_path=str(tmp_path / "demo.db"))
    runs = store.list_runs(limit=10)
    assert len(runs) >= 3, f"expected 3 demo runs, got {len(runs)}"
    # Each demo's frames + metrics must be present.
    for run in runs[:3]:
        frames = store.get_story_frames(run.id)
        metrics = store.get_metric_events(run.id)
        assert frames, f"demo run {run.name!r} produced no frames"
        assert metrics, f"demo run {run.name!r} produced no metrics"
