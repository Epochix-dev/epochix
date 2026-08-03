"""A run pushed through the event API must end up graded, not blank.

`POST /runs/{id}/event` is how the VS Code extension persists a parsed log.
The frames it produced were always correct, but nothing wrote the summary back
to the run row, so every run saved this way showed up as:

    ⟳  01KZ...  [-]  custom  my run

— no grade, task `custom`, and the running spinner forever. The values were the
placeholders set at creation and never revised. Only visible by listing runs
after pushing some, which no test did.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.server.app import create_app


@contextmanager
def _client() -> Iterator[TestClient]:
    """TestClient as a context manager — the lifespan sets up app.state.

    Constructing TestClient without entering it skips the lifespan, so
    `app.state.store` never exists and every request 500s.
    """
    with TestClient(create_app(Settings(db=":memory:"))) as client:
        yield client


def _push(client: TestClient, run_id: str, *, finish: bool) -> None:
    """Eight epochs of improving accuracy plus a falling loss."""
    seq = 0
    for epoch in range(1, 9):
        for key, value in (
            ("val_accuracy", 0.50 + epoch * 0.05),
            ("train_loss", 1.5 - epoch * 0.12),
        ):
            seq += 1
            last = finish and epoch == 8 and key == "train_loss"
            resp = client.post(
                f"/api/runs/{run_id}/event",
                json={
                    "seq": seq,
                    "epoch": epoch,
                    "canonical_key": key,
                    "raw_key": key,
                    "value": value,
                    "finished": last,
                },
            )
            assert resp.status_code == 202, resp.text


def test_pushed_run_gets_a_grade_and_the_task_it_was_created_with() -> None:
    with _client() as client:
        run_id = client.post("/api/runs", json={"name": "pushed", "task": "classification"}).json()[
            "id"
        ]

        _push(client, run_id, finish=True)

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["final_grade"] is not None, "run row never got a grade; only the frames had one"
        assert run["task_type"] == "classification", "task fell back to the creation placeholder"
        # The primary metric must be one that was actually sent. It used to read
        # `val_loss` — the default at creation — which was never pushed at all.
        assert run["primary_metric"] == "val_accuracy"
        assert run["finished_at"] is not None, "finished=true did not close the run"


def test_summary_is_current_before_the_run_is_finished() -> None:
    """The grade should track the run, not appear only at the end.

    A live run that is never finished (the client crashed, the log is still
    being written) must still show its grade so far, rather than nothing.
    """
    with _client() as client:
        run_id = client.post("/api/runs", json={"name": "still going"}).json()["id"]

        _push(client, run_id, finish=False)

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["final_grade"] is not None
        assert run["primary_metric"] == "val_accuracy"
        # ...but it must NOT claim to be over.
        assert run["finished_at"] is None, "run marked finished without being told it was"
