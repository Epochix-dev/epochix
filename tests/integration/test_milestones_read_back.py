"""A run's milestones come back from the store, to the dashboard and the reports.

They were written beside each frame and never read: `get_story_frames` built
every frame with no milestones and nothing selected from the table, so a page
opened on a run, the HTML export and the Markdown export showed none. The two a
run ends with (`biggest_jump`, `training_complete`) were published to an open
page and never stored at all.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epochix import parse
from epochix.config import Settings
from epochix.exporters.json_export import build_json_payload
from epochix.exporters.markdown_export import build_markdown
from epochix.i18n import t
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import Milestone, StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.app import create_app
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
KERAS = ROOT / "tests" / "fixtures" / "logs" / "keras_50ep.log"
LOGS = {
    **{p.name: p for p in (ROOT / "demo").glob("*.log")},
    **{p.name: p for p in (ROOT / "tests" / "fixtures" / "logs").glob("*.log")},
}


@pytest.fixture(scope="module")
def keras_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    db = str(tmp_path_factory.mktemp("ms") / "runs.db")
    run = parse(KERAS, db=db)
    return db, run.id


def test_the_snapshot_lists_every_milestone_and_each_frame_carries_its_own(
    keras_run: tuple[str, str],
) -> None:
    db, run_id = keras_run
    with TestClient(create_app(settings=Settings(db=db))) as client:
        body = client.get(f"/api/snapshot/{run_id}").json()

    listed = [(m["seq"], m["kind"]) for m in body["milestones"]]
    kinds = [kind for _, kind in listed]
    assert "first_above_25" in kinds, listed
    assert kinds[-1] == "training_complete", listed
    assert "biggest_jump" in kinds, listed
    assert listed == sorted(listed, key=lambda sk: sk[0]), "not in the order reached"

    on_frames = [(m["seq"], m["kind"]) for f in body["frames"] for m in f["milestones"]]
    assert on_frames, "no frame came back with its milestones"
    assert on_frames == [sk for sk in listed if sk[1] != "training_complete"]
    for f in body["frames"]:
        assert all(m["seq"] == f["seq"] for m in f["milestones"]), f["seq"]


def test_the_biggest_jump_sits_at_the_frame_where_the_metric_rose_most(
    keras_run: tuple[str, str],
) -> None:
    db, run_id = keras_run
    store = RunStore(db)
    frames = store.get_story_frames(run_id)
    (jump,) = [m for m in store.get_milestones(run_id) if m.kind == "biggest_jump"]
    # The story's metric is one series here (val_accuracy, higher is better):
    # the largest rise between consecutive frames is the jump's frame.
    assert len({f.primary_metric for f in frames}) == 1
    gains = [
        (b.primary_metric_value - a.primary_metric_value, b)
        for a, b in zip(frames, frames[1:], strict=False)
    ]
    best_gain, at = max(gains, key=lambda g: g[0])
    assert jump.seq == at.seq
    assert jump.epoch == at.epoch
    assert jump.value == pytest.approx(best_gain)
    assert jump.epoch != frames[-1].epoch, "stamped with the run's last epoch"


def test_the_json_and_html_payload_carries_them(keras_run: tuple[str, str]) -> None:
    db, run_id = keras_run
    store = RunStore(db)
    payload = build_json_payload(run_id, store)
    assert payload["milestones"] == [
        m.model_dump(mode="json") for m in store.get_milestones(run_id)
    ]
    assert any(f["milestones"] for f in payload["frames"])
    json.dumps(payload)  # what the HTML export embeds must serialise


def test_the_markdown_report_lists_them_with_their_epochs(keras_run: tuple[str, str]) -> None:
    db, run_id = keras_run
    store = RunStore(db)
    md = build_markdown(run_id, store)
    assert "## Milestones" in md
    section = md.split("## Milestones", 1)[1].split("\n## ", 1)[0]
    for m in store.get_milestones(run_id):
        assert m.message in section, m
        if m.epoch is not None:
            assert f"{m.message}** ({t('cover.epoch_n', 'en')} {m.epoch:g})" in section, m


def _told(path: Path) -> tuple[list[StoryFrame], list[Milestone]]:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("c", str(path)), run_id="c", store=store, hub=Hub())
    )
    return store.get_story_frames("c"), store.get_milestones("c")


@pytest.mark.parametrize("name", sorted(LOGS))
def test_every_log_reads_its_milestones_back_onto_their_frames(name: str) -> None:
    frames, milestones = _told(LOGS[name])
    if not frames:
        assert not milestones, "milestones without a story"
        return
    by_seq = {f.seq: f for f in frames}
    kinds = [m.kind for m in milestones]
    assert kinds.count("training_complete") == 1, kinds
    for m in milestones:
        if m.kind == "training_complete":
            assert m.seq not in by_seq
            continue
        frame = by_seq.get(m.seq)
        assert frame is not None, f"{m.kind} at seq {m.seq} has no frame"
        assert m in frame.milestones, m
        assert m.epoch == frame.epoch, m


def test_the_corpus_is_there() -> None:
    assert len(LOGS) >= 39, "the corpus went missing"
