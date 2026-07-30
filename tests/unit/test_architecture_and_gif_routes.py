"""A client that parsed the log itself must be able to hand over what it found.

The extension parses locally and pushes the result, so the server never sees the
file. Before this, ``RunCreateRequest`` had no way to carry the model summary,
and the Network State panel read "No architecture to display" for a log that
plainly contained one — 53,002 params of Keras summary sitting in demo.log.

The GIF route is here for a blunter reason: ``build_gif`` worked and was
reachable from the CLI, but no HTTP route served it, so no button in any UI
could ever have called it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.server.app import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An in-memory database, matching the pattern in tests/integration/test_api.py.

    Two reasons, both learned the hard way. The store must be handed over as
    ``Settings(db=...)`` — the settings field is ``db``, so the
    ``EPOCHIX_DB_PATH`` env var this fixture first used was simply ignored and
    the tests wrote into the developer's real run database. And an on-disk
    SQLite file under ``tmp_path`` leaves a handle open on Windows, where the
    teardown cannot then remove it.

    It must also be entered as a context manager: ``app.state.store`` is built
    by the lifespan handler, which a bare ``TestClient(app)`` never runs.
    """
    app = create_app(settings=Settings(db=":memory:"))
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


_ARCH = [
    {"name": "conv2d", "type": "Conv2D", "params": 320},
    {"name": "dense_1", "type": "Dense", "params": 1290},
]


def test_architecture_survives_the_round_trip(client: TestClient) -> None:
    run_id = client.post("/api/runs", json={"name": "demo.log", "architecture": _ARCH}).json()["id"]

    served = client.get(f"/api/snapshot/{run_id}").json()["run"]["config"]["architecture"]
    assert served == _ARCH, "the panel reads this straight off run.config"


def test_a_run_created_without_architecture_is_unaffected(client: TestClient) -> None:
    """The field is optional — the SDK and CLI paths supply it elsewhere."""
    run_id = client.post("/api/runs", json={"name": "no-arch"}).json()["id"]
    assert "architecture" not in client.get(f"/api/snapshot/{run_id}").json()["run"]["config"]


def _run_with_curve(client: TestClient) -> str:
    run_id = client.post("/api/runs", json={"name": "curve"}).json()["id"]
    for i in range(1, 11):
        client.post(
            f"/api/runs/{run_id}/event",
            json={
                "seq": i,
                "epoch": i,
                "canonical_key": "val_accuracy",
                "raw_key": "val_acc",
                "value": 0.5 + 0.04 * i,
            },
        )
    return run_id


def test_the_gif_route_serves_a_real_gif(client: TestClient) -> None:
    pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

    res = client.get(f"/api/export/{_run_with_curve(client)}/gif")

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/gif"
    assert res.content[:6] in (b"GIF87a", b"GIF89a"), "not actually a GIF"
    assert "attachment;" in res.headers["content-disposition"]


def test_a_run_with_nothing_to_animate_is_a_400_not_a_500(client: TestClient) -> None:
    """An empty run is the caller's situation, not a server fault, and the
    message has to say which."""
    pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

    run_id = client.post("/api/runs", json={"name": "empty"}).json()["id"]
    res = client.get(f"/api/export/{run_id}/gif")

    assert res.status_code == 400
    assert "animate" in res.json()["detail"]


def test_an_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/api/export/does-not-exist/gif").status_code == 404


def _run_with(client: TestClient, name: str, vals: list[float]) -> str:
    run_id = client.post("/api/runs", json={"name": name, "primary_metric": "val_accuracy"}).json()[
        "id"
    ]
    for i, v in enumerate(vals, start=1):
        client.post(
            f"/api/runs/{run_id}/event",
            json={
                "seq": i,
                "epoch": i,
                "canonical_key": "val_accuracy",
                "raw_key": "val_acc",
                "value": v,
            },
        )
    return run_id


def test_the_comparison_race_serves_a_real_gif(client: TestClient) -> None:
    pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

    a = _run_with(client, "baseline", [0.6 + 0.02 * i for i in range(10)])
    b = _run_with(client, "tuned", [0.7 + 0.02 * i for i in range(10)])

    res = client.get(f"/api/export/compare/gif?runs={a},{b}")

    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/gif"
    assert res.content[:6] in (b"GIF87a", b"GIF89a")


def test_a_race_needs_more_than_one_run(client: TestClient) -> None:
    pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

    only = _run_with(client, "solo", [0.6, 0.7, 0.8])
    res = client.get(f"/api/export/compare/gif?runs={only}")

    assert res.status_code == 400
    assert "at least two" in res.json()["detail"]


def test_the_compare_path_is_not_shadowed_by_a_run_id(client: TestClient) -> None:
    """`/compare/gif` and `/{run_id}/gif` are both two segments, so declaration
    order decides which wins. If this regresses the race route becomes a 404
    for a run that does not exist."""
    res = client.get("/api/export/compare/gif?runs=nope,also-nope")
    assert res.status_code == 404, "should reject the unknown runs, not miss the route"
