"""The Python SDK as `docs/api.md` documents it: parse, then use the run.

`export`, `compare`, `visualize`, `serve` and `parse_string` are all listed
there, and until 2026-11-10 no test had called one of them. Run by hand:

* `export(parse("train.log"))` raised "Run not found" in every format.
  `parse()` keeps the run in memory unless given `db=`; the others looked in
  the configured database.
* `compare(a, b)` returned its verdict with an empty narrative, for the same
  reason, without a word: the failed lookup is swallowed.
* `visualize(run, db=...)` ignored `db`. The app's startup opened the
  configured database over the store it had just been given.
* `serve(db=...)` read `db` nowhere.
* `export(run, "gif")` returned the path of a file it had not written.

Every test here calls the function the way the docs do, with no `db=`, against
the real store, exporters and server. The configured database is pointed at a
file that must still not exist afterwards: the journey works from memory, and
a failure cannot reach a developer's own runs.
"""

from __future__ import annotations

import gc
import json
import socket
import threading
import time
import webbrowser
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from epochix import compare, export, parse, parse_string, serve, visualize
from epochix.sdk import _stores
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "tests/fixtures/corpus_truth.json").read_text(encoding="utf-8"))
LOG = "pytorch_lightning.log"
# Two recorded runs told on the same metric from their first frame.
AHEAD = "keras_image_classifier.log"
BEHIND = "huggingface_bert.log"


def _path(log: str) -> Path:
    return ROOT / TRUTH[log]["path"]


@pytest.fixture(autouse=True)
def configured_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Exports land in a scratch folder; the configured DB is a path to watch."""
    db = tmp_path / "configured" / "runs.db"
    monkeypatch.setenv("EPOCHIX_DB", str(db))
    monkeypatch.chdir(tmp_path)
    return db


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def servers(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[uvicorn.Server]]:
    """Every server the SDK starts, so the test can stop it.

    The real `uvicorn.Server`, only recorded: `visualize(blocking=False)`
    returns a URL and no handle, and `serve()` never returns.
    """
    started: list[uvicorn.Server] = []

    class Recorded(uvicorn.Server):
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            super().__init__(*args, **kwargs)
            started.append(self)

    monkeypatch.setattr(uvicorn, "Server", Recorded)
    yield started
    for server in started:
        server.should_exit = True
    deadline = time.monotonic() + 10
    while any(server.started for server in started) and time.monotonic() < deadline:
        time.sleep(0.05)


def _get(url: str) -> httpx.Response:
    """GET *url* once the server answers; the last error if it never does."""
    deadline = time.monotonic() + 20
    while True:
        try:
            return httpx.get(url, timeout=5)
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


# ── parse → export ────────────────────────────────────────────────────────────


def test_a_parsed_run_is_exported_with_no_db_argument(configured_db: Path) -> None:
    truth = TRUTH[LOG]
    run = parse(_path(LOG))
    assert run.final_grade is not None
    assert run.final_grade.value == truth["final_grade"]

    as_json = export(run, "json")
    payload = json.loads(as_json.read_text(encoding="utf-8"))
    assert payload["run"]["id"] == run.id
    assert payload["run"]["final_grade"] == truth["final_grade"]
    assert len(payload["frames"]) == truth["frames"]
    assert payload["frames"][-1]["primary_metric_value"] == truth["last_value"]

    as_md = export(run, "md")
    assert truth["final_grade"] in as_md.read_text(encoding="utf-8")

    as_pdf = export(run, "pdf")
    assert as_pdf.read_bytes().startswith(b"%PDF-")

    # Default names, in the working directory, as the docstring says.
    assert {as_json.name, as_md.name, as_pdf.name} == {
        f"{run.id}.json",
        f"{run.id}.md",
        f"{run.id}.pdf",
    }
    assert as_json.parent == Path.cwd().resolve()

    # HTML inlines the dashboard bundle, which a source checkout does not
    # have. Either way the run itself must have been found.
    try:
        as_html = export(run, "html")
    except FileNotFoundError as exc:
        assert "bundle" in str(exc).lower()
    else:
        assert run.id in as_html.read_text(encoding="utf-8")

    assert not configured_db.exists(), "the journey touched the configured database"


def test_output_names_the_file(tmp_path: Path) -> None:
    out = export(parse(_path(LOG)), "md", output=tmp_path / "report.md")
    assert out == (tmp_path / "report.md").resolve()
    assert out.stat().st_size > 0


def test_a_run_parsed_into_a_file_is_found_there_too(tmp_path: Path, configured_db: Path) -> None:
    kept = tmp_path / "kept.db"
    run = parse(_path(LOG), db=str(kept))
    assert json.loads(export(run, "json").read_text(encoding="utf-8"))["run"]["id"] == run.id
    assert not configured_db.exists()


def test_parse_string_tells_the_same_story_and_exports() -> None:
    truth = TRUTH[LOG]
    run = parse_string(_path(LOG).read_text(encoding="utf-8"))
    assert run.task_type.value == truth["task"]
    assert run.primary_metric == truth["metric"]
    assert run.final_grade is not None
    assert run.final_grade.value == truth["final_grade"]
    payload = json.loads(export(run, "json").read_text(encoding="utf-8"))
    assert len(payload["frames"]) == truth["frames"]


def test_an_unknown_format_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    run = parse(_path(LOG))
    out = tmp_path / "run.gif"
    with pytest.raises(ValueError, match="Unknown export format 'gif'"):
        export(run, "gif", output=out)  # type: ignore[arg-type]
    assert not out.exists()


def test_a_run_that_is_not_there_says_where_it_looked(tmp_path: Path, configured_db: Path) -> None:
    """A run nobody parsed in this process is looked for in the configured DB."""
    kept = tmp_path / "kept.db"
    parsed = parse(_path(LOG), db=str(kept))
    loaded = RunStore(db_path=str(kept)).get_run(parsed.id)
    assert loaded is not None
    del parsed
    gc.collect()

    out = tmp_path / "missing.md"
    with pytest.raises(ValueError, match="Run not found") as refused:
        export(loaded, "md", output=out)
    assert str(configured_db) in str(refused.value)
    assert "db=" in str(refused.value)
    assert not out.exists()

    assert export(loaded, "md", output=out, db=str(kept)).stat().st_size > 0


def test_the_store_is_kept_only_as_long_as_the_run() -> None:
    """A loop over a thousand logs must not hold a thousand databases."""
    before = len(_stores._parsed_into)
    run = parse(_path(LOG))
    assert _stores._parsed_into[run.id].get_run(run.id) is not None
    again = parse(_path(LOG), run_id=run.id)
    newer = _stores._parsed_into[run.id]

    # The first run going away must not take the second one's note with it.
    del run
    gc.collect()
    assert _stores._parsed_into[again.id] is newer

    del again
    gc.collect()
    assert len(_stores._parsed_into) == before


# ── compare ───────────────────────────────────────────────────────────────────


def test_two_parsed_runs_are_compared_with_a_narrative(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ahead, behind = TRUTH[AHEAD], TRUTH[BEHIND]
    assert (ahead["final_grade"], behind["final_grade"]) == ("A+", "B+")
    assert ahead["metric"] == behind["metric"] == "val_accuracy"
    a = parse(_path(AHEAD), run_name="keras")
    b = parse(_path(BEHIND), run_name="bert")

    diff = compare(a, b)
    assert diff.better == "a"
    assert diff.grade_delta == "A+ vs B+"
    # The part that needs each run's frames, read from two separate stores:
    # both runs by name, each with the last value it reached.
    assert diff.narrative, "the narrative came back empty"
    assert "keras" in diff.narrative and "bert" in diff.narrative
    assert str(ahead["last_value"]) in diff.narrative
    assert str(behind["last_value"]) in diff.narrative

    diff.show()
    shown = capsys.readouterr().out
    assert "[A+]" in shown and "[B+]" in shown
    assert "Run A wins" in shown


# ── visualize / serve ─────────────────────────────────────────────────────────


def test_visualize_serves_the_run_that_was_parsed(
    servers: list[uvicorn.Server], monkeypatch: pytest.MonkeyPatch, configured_db: Path
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    run = parse(_path(LOG))
    port = _free_port()

    url = visualize(run, port=port, blocking=False)

    assert url == f"http://127.0.0.1:{port}/v/{run.id}"
    assert opened == [url]
    snapshot = _get(f"http://127.0.0.1:{port}/api/snapshot/{run.id}")
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    assert body["run"]["id"] == run.id
    assert body["total_frames"] == TRUTH[LOG]["frames"]
    assert body["frames"][-1]["primary_metric_value"] == TRUTH[LOG]["last_value"]
    assert len(servers) == 1
    assert not configured_db.exists()


def test_visualize_refuses_a_run_it_cannot_find_before_opening_anything(
    servers: list[uvicorn.Server], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    run = parse(_path(LOG))

    with pytest.raises(ValueError, match="Run not found"):
        visualize(run, port=_free_port(), db=str(tmp_path / "empty.db"), blocking=False)

    assert opened == []
    assert servers == []


def test_serve_serves_the_database_it_is_given(
    servers: list[uvicorn.Server], tmp_path: Path, configured_db: Path
) -> None:
    kept = tmp_path / "kept.db"
    run = parse(_path(LOG), db=str(kept))
    port = _free_port()

    # serve() blocks until its server is stopped, which the fixture does.
    thread = threading.Thread(
        target=serve, kwargs={"port": port, "db": str(kept), "open_browser": False}, daemon=True
    )
    thread.start()

    listed = _get(f"http://127.0.0.1:{port}/api/runs")
    assert listed.status_code == 200, listed.text
    assert [r["id"] for r in listed.json()["runs"]] == [run.id]
    assert not configured_db.exists()

    servers[0].should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "serve() did not return when its server stopped"
