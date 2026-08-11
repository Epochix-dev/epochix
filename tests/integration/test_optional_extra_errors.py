"""Missing optional extras must instruct, not 500.

Found by cold-installing the published wheel — no extras — and hitting every
export route the way a tester would. `gif` answered 501 with "pip install
'epochix[gif]'"; `pdf` answered 500, because `build_pdf` raises `ImportError`
while the route caught only `NotImplementedError`.

A 500 tells a tester the product is broken. A 501 with the package name tells
them what to do. The difference decides whether that becomes a bug report.
"""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.server.app import create_app

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _run_with_data(client: TestClient) -> str:
    run_id = client.post("/api/runs", json={"name": "extras", "task": "classification"}).json()[
        "id"
    ]
    for epoch in range(1, 6):
        client.post(
            f"/api/runs/{run_id}/event",
            json={
                "seq": epoch,
                "epoch": epoch,
                "canonical_key": "val_accuracy",
                "raw_key": "val_accuracy",
                "value": 0.5 + epoch * 0.05,
                "finished": epoch == 5,
            },
        )
    return run_id


@pytest.mark.parametrize(
    ("fmt", "module", "package"),
    [
        ("pdf", "weasyprint", "epochix[pdf]"),
        ("gif", "PIL", "epochix[gif]"),
    ],
)
def test_missing_extra_returns_501_with_the_package_name(
    fmt: str, module: str, package: str
) -> None:
    if importlib.util.find_spec(module) is not None:
        pytest.skip(f"{module} is installed; this asserts the ABSENT path")

    with TestClient(create_app(Settings(db=":memory:"))) as client:
        run_id = _run_with_data(client)
        resp = client.get(f"/api/export/{run_id}/{fmt}")

    assert resp.status_code == 501, f"got {resp.status_code}: a 500 reads as 'broken'"
    detail = resp.json().get("detail", "")
    assert package.split("[")[0] in detail and "install" in detail.lower(), detail


def test_formats_that_need_no_extra_still_work() -> None:
    """Guard the guard: if these broke, the test above could pass vacuously."""
    with TestClient(create_app(Settings(db=":memory:"))) as client:
        run_id = _run_with_data(client)
        for fmt in ("json", "md", "html"):
            resp = client.get(f"/api/export/{run_id}/{fmt}")
            assert resp.status_code == 200, f"{fmt}: {resp.status_code}"
            assert len(resp.content) > 0
