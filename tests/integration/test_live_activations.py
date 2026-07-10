"""LiveReporter activation transport: real captured scalars → run.config +
an ``activations`` WS broadcast, without spinning the uvicorn server thread.

The end-to-end server path is exercised by the manual GPU smoke run; here we
pin the deterministic transport contract the frontend relies on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epochix.enums import TaskType
from epochix.models import Run
from epochix.sdk.activations import ActivationCapturer
from epochix.sdk.live_reporter import LiveReporter
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore


def _make_run(run_id: str) -> Run:
    return Run(
        id=run_id,
        name="test",
        task_type=TaskType.GAZE,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="val_mae_cm",
        parser_used="sdk",
        config={"architecture": [{"name": "fc1"}]},
    )


def test_emit_persists_and_broadcasts_real_activations() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn

    store = RunStore(":memory:")
    run_id = "run1"
    store.create_run(_make_run(run_id))

    hub = Hub()
    published: list[object] = []
    orig = hub.publish
    hub.publish = lambda rid, msg: (published.append(msg), orig(rid, msg))[1]  # type: ignore[assignment]

    model = nn.Sequential(nn.Linear(6, 12), nn.ReLU(), nn.Linear(12, 3))
    cap = ActivationCapturer(model, hz=1000.0, gradients=False)
    model.train()
    model(torch.randn(4, 6))
    snapshot = cap.snapshot()
    cap.remove()
    assert snapshot  # sanity: capture produced something

    reporter = LiveReporter(task="gaze", open_browser=False)
    emit = reporter._make_emit(store, hub, run_id=run_id)
    emit(snapshot)

    # Persisted alongside (not clobbering) the existing architecture config.
    cfg = store.get_run(run_id).config  # type: ignore[union-attr]
    assert cfg["architecture"] == [{"name": "fc1"}]
    assert cfg["activations"] == snapshot
    for stats in cfg["activations"].values():
        assert stats["mag"] >= 0.0
        assert 0.0 <= stats["dead"] <= 1.0

    # Broadcast as an ``activations`` message carrying the layer map.
    act_msgs = [m for m in published if getattr(m, "type", None) == "activations"]
    assert len(act_msgs) == 1
    assert act_msgs[0].payload["layers"] == snapshot


def test_emit_swallows_store_errors() -> None:
    """Telemetry must never break training: a failing store is silently ignored."""

    class _BoomStore:
        def get_run(self, _run_id: str) -> object:
            raise RuntimeError("db down")

    reporter = LiveReporter(task="gaze", open_browser=False)
    emit = reporter._make_emit(_BoomStore(), Hub(), run_id="x")
    emit({"fc1": {"mag": 0.5, "dead": 0.0}})  # must not raise
