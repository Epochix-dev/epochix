"""Exports must speak the language the run was narrated in.

The narratives and the dashboard UI were translated into English, Farsi and
French from the start. The exports never were: every builder took
``(run_id, store)`` and nothing else, so a Farsi run produced a report whose
sentences were Farsi and whose every heading was English. Worse, the CLI had no
``--locale`` at all — the translations existed and the primary interface could
not reach them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from epochix.enums import Grade, Phase, TaskType
from epochix.exporters.markdown_export import build_markdown
from epochix.exporters.pdf_export import build_pdf
from epochix.i18n import SUPPORTED_LOCALES, t
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.store.sqlite_store import RunStore


def _store(tmp_path: Path, *, locale: str) -> tuple[str, RunStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(tmp_path / "i18n.db"))
    run_id = "01I18NTESTRUN"
    store.create_run(
        Run(
            id=run_id,
            name="localised run",
            task_type=TaskType.CLASSIFICATION,
            started_at=datetime.now(tz=timezone.utc),
            primary_metric="val_accuracy",
            parser_used="test",
            config={"locale": locale},
        )
    )
    for i in range(1, 5):
        store.append_metric_event(
            MetricEvent(
                run_id=run_id,
                seq=i,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(i),
                canonical_key="val_accuracy",
                raw_key="val_accuracy",
                value=0.4 + i * 0.1,
            )
        )
        store.append_story_frame(
            StoryFrame(
                run_id=run_id,
                seq=i,
                epoch=float(i),
                phase=Phase.LEARNING,
                grade=Grade.B,
                primary_metric="val_accuracy",
                primary_metric_value=0.4 + i * 0.1,
                narrative="narrative text",
                progress=0.5,
                confidence=0.8,
                task_type=TaskType.CLASSIFICATION,
            )
        )
    store.finish_run(run_id, final_grade=Grade.B, story_summary="summary")
    return run_id, store


class TestTheStringTable:
    def test_every_locale_has_every_key(self) -> None:
        from epochix.i18n import _EN, _FA, _FR

        assert set(_FA) == set(_EN), set(_EN) ^ set(_FA)
        assert set(_FR) == set(_EN), set(_EN) ^ set(_FR)

    def test_an_unknown_locale_falls_back_rather_than_failing(self) -> None:
        """A run from a newer client, or a user typing `de`, gets English —
        not a crash in the middle of an export."""
        assert t("pdf.epochs", "de") == t("pdf.epochs", "en")

    def test_an_unknown_key_returns_itself(self) -> None:
        assert t("no.such.key", "fr") == "no.such.key"


class TestMarkdownIsLocalised:
    """Markdown is UTF-8, so unlike the PDF it carries every locale we ship."""

    @pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
    def test_headings_use_the_runs_language(self, locale: str, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path / locale, locale=locale)
        md = build_markdown(run_id, store)
        assert t("md.summary", locale) in md
        assert t("md.grade", locale) in md

    def test_farsi_really_is_farsi(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path / "fa", locale="fa")
        md = build_markdown(run_id, store)
        assert "نمره" in md
        assert "| **Grade** |" not in md


class TestThePdfDoesNotPretend:
    """The PDF's core fonts are Latin-1.

    Localising it made Farsi *worse*: headings, labels and narrative all became
    question marks, so even the structure stopped being navigable. It now falls
    back to English chrome and says why.
    """

    def test_a_drawable_locale_is_translated(self, tmp_path: Path) -> None:
        from tests.unit.test_pdf_charts import _pdf_text

        run_id, store = _store(tmp_path / "fr", locale="fr")
        assert t("pdf.epochs", "fr") in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_an_undrawable_locale_never_emits_question_marks(self, tmp_path: Path) -> None:
        from tests.unit.test_pdf_charts import _pdf_text

        run_id, store = _store(tmp_path / "fa", locale="fa")
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "?" not in text

    def test_it_says_why_it_is_in_english(self, tmp_path: Path) -> None:
        from tests.unit.test_pdf_charts import _pdf_text

        run_id, store = _store(tmp_path / "fa2", locale="fa")
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "cannot draw" in text
        assert "Markdown" in text
