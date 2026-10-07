"""Every report says how its grade was reached — and a server started away from
the project still finds the project's thresholds.

0.7.29 put `grade_basis` on each frame, and the dashboard card and the Markdown
report said it. The PDF cover and the run comparison (Markdown and PDF) did
not: a run graded on how far its loss fell read there as if it had been graded
on a scale, and two runs graded the two different ways sat side by side with
letters that do not compare.

`EPOCHIX_GRADE_CONFIG` could name a file or switch the lookup off. The VS Code
extension starts its server in a temporary folder and passed the path of the
workspace's file — when there was one at start-up. A file created afterwards
was never found. A folder can now be named, and is searched like the working
directory.
"""

from __future__ import annotations

import asyncio
import re
import zlib
from pathlib import Path

import pytest

from epochix.exporters.compare_export import build_comparison_markdown, build_comparison_pdf
from epochix.exporters.pdf_export import build_pdf
from epochix.i18n import t
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.config_loader import active_grade_config, configured_path

REPO = Path(__file__).resolve().parents[2]
KERAS = REPO / "demo" / "keras_image_classifier.log"  # graded on thresholds
XGBOOST = REPO / "tests" / "fixtures" / "logs" / "xgboost_real_classifier.log"  # on improvement


def _store(locale: str, *logs: Path) -> tuple[RunStore, list[str]]:
    store = RunStore(":memory:")
    ids = []
    for i, log in enumerate(logs):
        assert log.stat().st_size > 0
        run_id = f"r{i}"
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester(run_id, str(log)),
                run_id=run_id,
                store=store,
                hub=Hub(),
                locale=locale,
            )
        )
        ids.append(run_id)
    return store, ids


def _pdf_text(pdf: bytes) -> bytes:
    """The text drawn on every page, joined (Latin-1 core font: plain Tj strings)."""
    pages = re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S)
    out = []
    for page in pages:
        try:
            out += re.findall(rb"\((.*?)\) ?Tj", zlib.decompress(page))
        except zlib.error:
            continue
    return b" ".join(out)


def _words(sentence: str) -> bytes:
    """A sentence as the PDF holds it once its wrapped lines are joined."""
    return sentence.encode("latin-1")


class TestThePdfCover:
    @pytest.mark.parametrize("locale", ["en", "fr"])
    @pytest.mark.parametrize(
        ("log", "basis"), [(KERAS, "thresholds"), (XGBOOST, "improvement")], ids=["keras", "xgb"]
    )
    def test_it_says_how_the_grade_was_reached(self, locale: str, log: Path, basis: str) -> None:
        store, (run_id,) = _store(locale, log)
        assert store.get_story_frames(run_id)[-1].grade_basis == basis, "premise"
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert _words(t(f"grade_basis.{basis}", locale)) in text, text[:400]
        other = "improvement" if basis == "thresholds" else "thresholds"
        assert _words(t(f"grade_basis.{other}", locale)) not in text


class TestTheComparison:
    def test_the_markdown_table_says_how_each_run_was_graded(self) -> None:
        store, ids = _store("en", KERAS, XGBOOST)
        md = build_comparison_markdown(ids, store)
        rows = [line for line in md.splitlines() if line.startswith("| ") and "**" in line]
        assert len(rows) == 2, md
        assert t("grade_basis.thresholds", "en") in rows[0]
        assert t("grade_basis.improvement", "en") in rows[1]
        assert t("md.grade_note", "en") in md, "the column is headed"

    def test_the_pdf_table_says_it_too(self) -> None:
        store, ids = _store("en", KERAS, XGBOOST)
        text = _pdf_text(build_comparison_pdf(ids, store))
        for basis in ("thresholds", "improvement"):
            sentence = t(f"grade_basis.{basis}", "en")
            # A table cell wraps its sentence over lines; every word is there.
            for word in sentence.rstrip(".").split():
                assert word.encode("latin-1") in text, (basis, word)

    def test_a_grade_note_still_follows_the_basis(self) -> None:
        store, ids = _store("en", KERAS, XGBOOST)
        keras_last = store.get_story_frames(ids[0])[-1]
        assert keras_last.grade_note == "still_improving", "premise"
        md = build_comparison_markdown(ids, store)
        row = next(line for line in md.splitlines() if line.startswith("| ") and "**A+**" in line)
        both = t("grade_basis.thresholds", "en") + " " + t("grade_note.still_improving", "en")
        assert both in row, row


STRICT = (
    'version: 1\ngrade_thresholds:\n  classification:\n    "A+": 0.999\n'
    "    A: 0.998\n    B: 0.997\n    C: 0.996\n    D: 0.995\n    F: 0.0\n"
)


class TestTheSettingMayNameAFolder:
    @pytest.fixture
    def setting(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        project = tmp_path / "project"
        (project / "experiments").mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")
        monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", str(project / "experiments"))
        return project

    def test_a_file_in_the_folder_or_above_it_is_used(self, setting: Path) -> None:
        assert configured_path() is None
        (setting / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        assert configured_path() == setting / ".epochix.yaml"
        config = active_grade_config()
        assert config is not None and "classification" in config.grade_thresholds

    def test_a_file_created_after_the_process_started_is_found(self, setting: Path) -> None:
        """What the extension's server needs: it is started before the file exists."""
        assert active_grade_config() is None
        (setting / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        assert active_grade_config() is not None
        (setting / ".epochix.yaml").unlink()
        assert active_grade_config() is None

    def test_a_run_through_the_pipeline_uses_it(self, setting: Path, tmp_path: Path) -> None:
        (setting / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        log = tmp_path / "run.log"
        log.write_text(
            "".join(
                f"Epoch {e}/5 train_loss={1 / e:.3f} val_accuracy={v}\n"
                for e, v in enumerate([0.58, 0.66, 0.74, 0.82, 0.90], 1)
            ),
            encoding="utf-8",
        )
        store, (run_id,) = _store("en", log)
        last = store.get_story_frames(run_id)[-1]
        assert (last.primary_metric_value, last.grade.value) == (0.90, "F")

    def test_a_file_is_still_named_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        named = tmp_path / "strict.yaml"
        named.write_text(STRICT, encoding="utf-8")
        monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", str(named))
        assert configured_path() == named
