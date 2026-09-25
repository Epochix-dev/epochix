"""A letter says when it deserves less weight than it looks.

An 11-epoch run and a 200-epoch run received equally confident letters, and a
two-reading run could show an A+ with nothing beside it. Two things the log
does show make a letter provisional: it rests on few readings, or the metric
was still setting new bests when it was taken. The engines record which
(``StoryFrame.grade_note``); the dashboard and the exports say it in the
reader's language. No confidence number is invented for it.
"""

from __future__ import annotations

import re
import sqlite3
import zlib
from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.enums import Grade
from epochix.exporters.markdown_export import build_markdown
from epochix.i18n import t
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.grade import FEW_READINGS, grade_note

if TYPE_CHECKING:
    from pathlib import Path

LOCALES = ("en", "fa", "fr")


class TestTheRule:
    def test_few_readings(self) -> None:
        for n in range(1, FEW_READINGS):
            assert grade_note(Grade.A, n, has_epoch=True, new_best=True) == "few_readings"

    def test_a_new_best_after_enough_readings_is_still_improving(self) -> None:
        assert grade_note(Grade.B, FEW_READINGS, has_epoch=True, new_best=True) == (
            "still_improving"
        )

    def test_a_settled_run_has_no_note(self) -> None:
        assert grade_note(Grade.B, 200, has_epoch=True, new_best=False) is None

    def test_a_fit_once_result_is_not_provisional(self) -> None:
        """No epoch and one reading is a finished result, not epoch one."""
        assert grade_note(Grade.A, 1, has_epoch=False, new_best=True) is None

    def test_an_incomplete_grade_has_nothing_to_qualify(self) -> None:
        assert grade_note(Grade.INCOMPLETE, 2, has_epoch=True, new_best=True) is None


def _parse(tmp_path: Path, lines: list[str], locale: str = "en") -> tuple[str, RunStore]:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t", locale=locale)
    return run.id, RunStore(db_path=db)


def _short() -> list[str]:
    return [
        f"Epoch {e}/2 train_loss={1.0 / e:.4f} val_accuracy={0.4 + 0.3 * e:.4f}" for e in (1, 2)
    ]


def _climbing(n: int = 8) -> list[str]:
    return [
        f"Epoch {e}/{n} train_loss={1.0 / e:.4f} val_accuracy={0.5 + 0.04 * e:.4f}"
        for e in range(1, n + 1)
    ]


def _settled() -> list[str]:
    acc = [0.60, 0.70, 0.78, 0.82, 0.84, 0.85, 0.84, 0.85, 0.84, 0.845]
    return [
        f"Epoch {e}/10 train_loss={1.0 / e:.4f} val_accuracy={a:.4f}" for e, a in enumerate(acc, 1)
    ]


class TestEndToEnd:
    """Through parse() and the store, as the dashboard and exports read it."""

    def test_a_two_epoch_run_is_provisional(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, _short())
        frames = store.get_story_frames(run_id)
        assert [f.grade_note for f in frames] == ["few_readings", "few_readings"]

    def test_a_run_still_climbing_says_so(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, _climbing())
        assert store.get_story_frames(run_id)[-1].grade_note == "still_improving"

    def test_a_settled_run_has_no_note(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, _settled())
        assert store.get_story_frames(run_id)[-1].grade_note is None

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_markdown_report_says_it(self, tmp_path: Path, locale: str) -> None:
        run_id, store = _parse(tmp_path, _short(), locale=locale)
        md = build_markdown(run_id=run_id, store=store)
        assert t("grade_note.few_readings", locale) in md
        assert t("md.grade_note", locale) in md

    def test_the_markdown_report_is_silent_when_there_is_nothing_to_say(
        self, tmp_path: Path
    ) -> None:
        run_id, store = _parse(tmp_path, _settled())
        md = build_markdown(run_id=run_id, store=store)
        assert t("md.grade_note", "en") not in md

    @pytest.mark.parametrize("locale", ["en", "fr"])
    def test_the_pdf_cover_says_it(self, tmp_path: Path, locale: str) -> None:
        # fpdf2 is a core dependency, so this runs everywhere — no skip to hide
        # behind. English and French are drawn in a Latin-1 core font, whose
        # text sits in the page stream as plain `(...) Tj` strings.
        from epochix.exporters.pdf_export import build_pdf

        run_id, store = _parse(tmp_path, _short(), locale=locale)
        pdf = build_pdf(run_id=run_id, store=store)
        first = re.search(rb"stream\r?\n(.*?)endstream", pdf, re.S)
        assert first is not None
        cover = b" ".join(re.findall(rb"\((.*?)\) ?Tj", zlib.decompress(first.group(1))))
        # multi_cell wraps the sentence over lines; joined, it reads whole.
        assert t("grade_note.few_readings", locale).encode("latin-1") in cover, cover


def test_an_existing_database_gains_the_column(tmp_path: Path) -> None:
    """A database created before grade_note existed is backfilled, not broken."""
    db = tmp_path / "old.db"
    RunStore(db_path=str(db))
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE story_frames DROP COLUMN grade_note")
    con.commit()
    con.close()

    log = tmp_path / "run.log"
    log.write_text("\n".join(_short()) + "\n", encoding="utf-8")
    run = parse(log, db=str(db), run_name="t")
    frames = RunStore(db_path=str(db)).get_story_frames(run.id)
    assert [f.grade_note for f in frames] == ["few_readings", "few_readings"]
