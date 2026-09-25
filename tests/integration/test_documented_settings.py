"""Settings documented in docs/config.md do what they say — or refuse.

Five were read by no code: EPOCHIX_SCRUB_SECRETS ("Redact secret-looking
strings from stored lines"), EPOCHIX_OPEN_BROWSER, EPOCHIX_POSTGRES_DSN,
EPOCHIX_REDIS_URL and EPOCHIX_TELEMETRY. The first is a security promise; a
user who turned it on kept every key their training script printed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from epochix.config import Settings, get_settings
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

KEY = "hf_abcdefghijklmnopqrstuvwxyz0123456789"
LOG = [
    f"HF_TOKEN={KEY}",
    "epoch=1 train_loss=0.90 val_accuracy=0.61",
    "epoch=2 train_loss=0.70 val_accuracy=0.72",
    "epoch=3 train_loss=0.55 val_accuracy=0.80",
]


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scrub: str | None) -> RunStore:
    if scrub is not None:
        monkeypatch.setenv("EPOCHIX_SCRUB_SECRETS", scrub)
    log = tmp_path / "train.log"
    log.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("s", str(log)),
            run_id="s",
            store=store,
            hub=Hub(),
            keep_raw_lines=True,
        )
    )
    return store


def test_stored_lines_are_scrubbed_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _run(tmp_path, monkeypatch, scrub=None)
    stored = "\n".join(store.get_raw_lines("s"))
    assert KEY not in stored, "a token was stored verbatim"
    assert "HF_TOKEN=[REDACTED]" in stored
    # The parsers read the line as printed: the metrics are untouched.
    values = [e.value for e in store.get_metric_events("s") if e.canonical_key == "val_accuracy"]
    assert values == [0.61, 0.72, 0.80]


def test_scrubbing_can_be_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _run(tmp_path, monkeypatch, scrub="false")
    assert KEY in "\n".join(store.get_raw_lines("s"))


@pytest.mark.parametrize("name", ["EPOCHIX_POSTGRES_DSN", "EPOCHIX_REDIS_URL"])
def test_an_unbuilt_backend_is_refused_not_ignored(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "postgresql://u:p@db/x")
    with pytest.raises(ValueError, match=f"{name} is set, but epochix has no hosted backend"):
        Settings()


def test_open_browser_off_opens_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import webbrowser

    from epochix.browser import open_in_browser

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    monkeypatch.setenv("EPOCHIX_OPEN_BROWSER", "false")
    assert get_settings().open_browser is False
    assert open_in_browser("http://127.0.0.1:1/v/x") is False
    assert opened == []

    monkeypatch.setenv("EPOCHIX_OPEN_BROWSER", "true")
    assert open_in_browser("http://127.0.0.1:1/v/x") is True
    assert opened == ["http://127.0.0.1:1/v/x"]


def test_no_code_path_opens_a_browser_behind_the_setting() -> None:
    """Every browser open goes through epochix.browser."""
    src = Path(__file__).resolve().parents[2] / "src" / "epochix"
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if p.name != "browser.py" and "webbrowser.open(" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
