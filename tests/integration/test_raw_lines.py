"""The log lines a run kept come back from `GET /api/raw/{run_id}`.

`EPOCHIX_KEEP_RAW_LINES` stored every line, and this endpoint is the only
reader of them — yet nothing called it, no test ran it, and no page said it
existed. A run read without the setting answered 200 with no lines, as if its
log had been empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epochix import parse
from epochix.config import Settings
from epochix.scrub import REDACTED
from epochix.server.app import create_app

LINES = [
    "wandb: logging in with password=not-a-real-one",
    *(
        f"Epoch {i}/4 train_loss={1 - i * 0.2:.2f} val_accuracy={0.5 + i * 0.1:.2f}"
        for i in range(1, 5)
    ),
]


def _read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, keep: bool) -> tuple[str, str]:
    log = tmp_path / "train.log"
    log.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    monkeypatch.setenv("EPOCHIX_KEEP_RAW_LINES", "true" if keep else "false")
    db = str(tmp_path / "runs.db")
    return db, parse(log, db=db).id


def test_a_kept_run_gives_back_its_lines_in_order_with_secrets_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, run_id = _read(tmp_path, monkeypatch, keep=True)
    with TestClient(create_app(settings=Settings(db=db))) as client:
        answer = client.get(f"/api/raw/{run_id}")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["lines"] == [f"wandb: logging in with password={REDACTED}", *LINES[1:]]
    assert body["total_lines"] == len(LINES)
    assert "not-a-real-one" not in answer.text


def test_a_run_read_without_the_setting_says_none_were_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, run_id = _read(tmp_path, monkeypatch, keep=False)
    with TestClient(create_app(settings=Settings(db=db))) as client:
        answer = client.get(f"/api/raw/{run_id}")
        missing = client.get("/api/raw/no-such-run")
    assert answer.status_code == 404
    assert "EPOCHIX_KEEP_RAW_LINES" in answer.json()["detail"]
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Run not found"


def test_the_lines_need_the_token_when_one_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They are the log as printed, less what the scrubber recognises."""
    db, run_id = _read(tmp_path, monkeypatch, keep=True)
    app = create_app(settings=Settings(db=db, auth_token="t0ken-for-this-test"))
    with TestClient(app) as client:
        refused = client.get(f"/api/raw/{run_id}")
        allowed = client.get(
            f"/api/raw/{run_id}", headers={"Authorization": "Bearer t0ken-for-this-test"}
        )
    assert refused.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["total_lines"] == len(LINES)
