"""Farsi in a PDF reads in the right order.

Every Farsi PDF since 0.7.15 scrambled word order in two ways, found by
rendering a page and reading it:

* fpdf2 takes a paragraph's direction from its first strong letter, so a Farsi
  sentence opening with a run name or a metric ("{a} و {b} …",
  "{metric} در دوره …") was laid out left to right, and the Farsi after a
  number came out reversed.
* fpdf2 misplaces text around a zero-width non-joiner, which written Farsi uses
  in almost every sentence (می‌شود, آن‌ها).

These check what fpdf2's own bidi algorithm makes of the text the renderer
hands it — over every Farsi template, message and label, and over the strings
a real Farsi report and comparison actually draw.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fpdf.bidi import BidiParagraph, TextDirection

from epochix import parse
from epochix.exporters import _pdf_render
from epochix.exporters._pdf_render import _rtl_safe
from epochix.i18n import _LOCALES
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.messages import MESSAGES

if TYPE_CHECKING:
    from collections.abc import Iterator

ZWNJ = "‌"
TEMPLATES = Path(_pdf_render.__file__).resolve().parents[1] / "story_engine" / "templates"

# Placeholders filled with the Latin text real runs put there: run names and
# metric keys are what open a sentence with a left-to-right letter.
FILL = {
    "{a}": "run-a",
    "{b}": "run-b",
    "{winner}": "lower-lr",
    "{loser}": "baseline",
    "{metric}": "val_accuracy",
    "{metrics}": "val_accuracy, val_loss",
    "{value}": "0.8412",
    "{value_pct}": "84.1%",
    "{best}": "0.8600",
    "{baseline}": "0.1010",
    "{delta}": "+0.0123",
    "{delta_pct}": "+1.2",
    "{gap}": "0.0171",
    "{epoch}": "7",
    "{best_epoch}": "5",
    "{last_epoch}": "6",
    "{epochs_seen}": "8",
    "{win_value}": "0.9020",
    "{lose_value}": "0.7610",
}


def _fill(text: str) -> str:
    for key, value in FILL.items():
        text = text.replace(key, value)
    return text


def _is_farsi(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def _every_farsi_string() -> Iterator[tuple[str, str]]:
    for path in sorted(TEMPLATES.rglob("*.fa.txt")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                yield f"{path.relative_to(TEMPLATES)}:{n}", _fill(line.strip())
    for key, text in MESSAGES["fa"].items():
        yield f"messages:{key}", _fill(text)
    for key, text in _LOCALES["fa"].items():
        yield f"i18n:{key}", _fill(text)


FARSI = [(where, text) for where, text in _every_farsi_string() if _is_farsi(text)]


def _lays_out_rtl(text: str) -> bool:
    return all(
        BidiParagraph(text=line).base_direction == TextDirection.RTL
        for line in text.split("\n")
        if line.strip()
    )


class TestTheRewrite:
    def test_a_sentence_opening_with_a_name_is_marked_right_to_left(self) -> None:
        text = "run-a و run-b تنها 0.0171 با هم فاصله دارند"
        assert not _lays_out_rtl(text), "premise: fpdf2 would lay this out left to right"
        assert _lays_out_rtl(_rtl_safe(text))

    def test_the_non_joiner_is_drawn_as_a_narrow_space(self) -> None:
        out = _rtl_safe("آن‌ها نیست")
        assert ZWNJ not in out
        assert "آن ها" in out

    def test_latin_text_is_untouched(self) -> None:
        for text in ("val_accuracy", "0.94 - 0.98", "run-a (1a2b)", "epochix · 01ABC"):
            assert _rtl_safe(text) == text

    def test_each_line_is_its_own_paragraph(self) -> None:
        out = _rtl_safe("سلام\nrun-a و run-b")
        first, second = out.split("\n")
        assert first == "سلام"
        assert second.startswith("‏")


class TestEveryFarsiString:
    def test_there_are_strings_to_check(self) -> None:
        # Guard: an empty glob would pass every check below by checking nothing.
        assert len(FARSI) >= 100
        assert any(not _lays_out_rtl(text) for _, text in FARSI), (
            "premise: some Farsi strings open with a Latin placeholder"
        )

    @pytest.mark.parametrize(("where", "text"), FARSI, ids=[w for w, _ in FARSI])
    def test_it_lays_out_right_to_left_without_a_non_joiner(self, where: str, text: str) -> None:
        out = _rtl_safe(text)
        assert _lays_out_rtl(out), where
        assert ZWNJ not in out, where


class _Recorder:
    """Every string a document is asked to draw, through the real renderer."""

    def __init__(self) -> None:
        self.drawn: list[str] = []

    def wrap(self, doc: Any) -> Any:  # noqa: ANN401 - fpdf2 ships no py.typed
        drawn = self.drawn
        cell, multi_cell = doc.cell, doc.multi_cell

        def rec_cell(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            text = kwargs.get("text", args[2] if len(args) > 2 else "")
            drawn.append(str(text))
            return cell(*args, **kwargs)

        def rec_multi_cell(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            text = kwargs.get("text", args[2] if len(args) > 2 else "")
            drawn.append(str(text))
            return multi_cell(*args, **kwargs)

        doc.cell, doc.multi_cell = rec_cell, rec_multi_cell
        return doc


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    pytest.importorskip("uharfbuzz")
    rec = _Recorder()
    make = _pdf_render._pdf
    monkeypatch.setattr(_pdf_render, "_pdf", lambda **kw: rec.wrap(make(**kw)))
    return rec


def _farsi_runs(tmp_path: Path) -> tuple[RunStore, list[str]]:
    db = tmp_path / "runs.db"
    ids = []
    for name, accs in (
        ("run-a", [0.6, 0.72, 0.8, 0.86, 0.9, 0.92]),
        ("run-b", [0.5, 0.55, 0.58, 0.6]),
    ):
        log = tmp_path / f"{name}.log"
        lines = [
            f"Epoch {e}/{len(accs)} train_loss={1 / e:.4f} val_accuracy={a:.4f}"
            for e, a in enumerate(accs, 1)
        ]
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ids.append(parse(log, db=str(db), run_name=name, locale="fa").id)
    return RunStore(db_path=str(db)), ids


def test_a_farsi_report_draws_only_right_to_left_farsi(tmp_path: Path, recorder: _Recorder) -> None:
    from epochix.exporters.pdf_export import build_pdf

    store, ids = _farsi_runs(tmp_path)
    build_pdf(ids[0], store)
    farsi = [s for s in recorder.drawn if _is_farsi(s)]
    assert len(farsi) >= 10, "the report drew almost no Farsi"
    for text in farsi:
        assert ZWNJ not in text, text
        assert _lays_out_rtl(text), text
