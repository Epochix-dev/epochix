"""Every export format works from `pip install epochix`. No extras.

This file used to assert the opposite — that `pdf` and `gif` returned 501 with
the name of the package to install. Both are core now (pillow, fpdf2), so the
invariant flipped: an export answering 501 for a missing dependency is itself
the bug.

The history is worth keeping, because it is why the extras went away:

* `gif` was behind an extra for no reason. pillow is a clean wheel.
* `pdf` used WeasyPrint, which needs GTK system libraries. `pip install
  weasyprint` SUCCEEDS on Windows and the import then dies loading
  libgobject-2.0-0 — so users who followed the instruction still could not
  export, and got a 500 telling them to install what they had just installed.
  fpdf2 is pure Python and renders the same report.
"""

from __future__ import annotations

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


@pytest.mark.parametrize(("fmt", "magic"), [("pdf", b"%PDF-"), ("gif", b"GIF8")])
def test_binary_exports_work_without_any_extra(fmt: str, magic: bytes) -> None:
    """The two that used to need an extra. Both ship in the base install now."""
    with TestClient(create_app(Settings(db=":memory:"))) as client:
        run_id = _run_with_data(client)
        resp = client.get(f"/api/export/{run_id}/{fmt}")

    assert resp.status_code == 200, f"{fmt}: {resp.status_code} — {resp.text[:200]}"
    assert resp.content.startswith(magic), resp.content[:16]
    assert len(resp.content) > 500


def test_text_exports_work_too() -> None:
    """Guard the guard: if these broke, the test above could pass vacuously.

    HTML is the exception — it embeds the built dashboard, which is vendored
    into the wheel at release time and absent from a source checkout, so 501
    is correct there. It must still EXPLAIN itself rather than just fail.
    """
    with TestClient(create_app(Settings(db=":memory:"))) as client:
        run_id = _run_with_data(client)
        for fmt in ("json", "md"):
            resp = client.get(f"/api/export/{run_id}/{fmt}")
            assert resp.status_code == 200, f"{fmt}: {resp.status_code}"
            assert len(resp.content) > 0

        resp = client.get(f"/api/export/{run_id}/html")
        assert resp.status_code in (200, 501), resp.status_code
        if resp.status_code == 501:
            assert "frontend" in resp.json().get("detail", "").lower()
