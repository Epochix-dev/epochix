"""Every setting a parameter search tried reaches the exports.

GridSearchCV fold rows were grouped by setting and the winner charted, but the
rest of what the folds said was read and then thrown away: ``epochix check``
listed the candidates, and no export could. The one thing a search exists to
show — how the settings compared — never left the terminal.

The fold readings are now kept on the run and ranked by one function for
``check``, the Markdown report, the PDF and the JSON export alike.
"""

from __future__ import annotations

import json
import re
import zlib
from statistics import fmean
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

import epochix.cli as cli
from epochix import parse
from epochix.cross_validation import record, summarise
from epochix.exporters.json_export import build_json
from epochix.exporters.markdown_export import build_markdown
from epochix.exporters.pdf_export import build_pdf
from epochix.i18n import t
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

# GridSearchCV(DecisionTreeClassifier(), {"criterion": [...], "max_depth": [3, 8]},
# cv=3, verbose=3) — four settings, three folds each.
GRID = [
    "Fitting 3 folds for each of 4 candidates, totalling 12 fits",
    "[CV 1/3] END .......criterion=gini, max_depth=3;, score=0.920 total time=   0.0s",
    "[CV 2/3] END .......criterion=gini, max_depth=3;, score=0.950 total time=   0.0s",
    "[CV 3/3] END .......criterion=gini, max_depth=3;, score=0.910 total time=   0.0s",
    "[CV 1/3] END .......criterion=gini, max_depth=8;, score=0.940 total time=   0.0s",
    "[CV 2/3] END .......criterion=gini, max_depth=8;, score=0.980 total time=   0.0s",
    "[CV 3/3] END .......criterion=gini, max_depth=8;, score=0.960 total time=   0.0s",
    "[CV 1/3] END ....criterion=entropy, max_depth=3;, score=0.900 total time=   0.0s",
    "[CV 2/3] END ....criterion=entropy, max_depth=3;, score=0.930 total time=   0.0s",
    "[CV 3/3] END ....criterion=entropy, max_depth=3;, score=0.890 total time=   0.0s",
    "[CV 1/3] END ....criterion=entropy, max_depth=8;, score=0.950 total time=   0.0s",
    "[CV 2/3] END ....criterion=entropy, max_depth=8;, score=0.940 total time=   0.0s",
    "[CV 3/3] END ....criterion=entropy, max_depth=8;, score=0.955 total time=   0.0s",
]
SETTINGS = [
    "criterion=gini, max_depth=3",
    "criterion=gini, max_depth=8",
    "criterion=entropy, max_depth=3",
    "criterion=entropy, max_depth=8",
]
WINNER = "criterion=gini, max_depth=8"

# The loop most people write: no settings, a printed mean.
HANDWRITTEN = [
    "Running 5-fold cross-validation...",
    "Fold 1: accuracy = 0.9375",
    "Fold 2: accuracy = 0.8938",
    "Fold 3: accuracy = 0.9187",
    "Fold 4: accuracy = 0.9062",
    "Fold 5: accuracy = 0.8688",
    "Mean accuracy: 0.9050 (+/- 0.0232)",
]


def _parse(tmp_path: Path, lines: list[str], locale: str = "en") -> tuple[str, RunStore]:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t", locale=locale)
    return run.id, RunStore(db_path=db)


def _pdf_text(pdf: bytes) -> bytes:
    """Every `(...) Tj` string in the document (Latin-1 core-font locales)."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            out += re.findall(rb"\((.*?)\) ?Tj", zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    # PDF string literals escape their own delimiters.
    return b" ".join(out).replace(b"\\(", b"(").replace(b"\\)", b")")


class TestRanking:
    def test_best_first_and_the_winner_is_chosen(self) -> None:
        cv = {"folds": {"score": [0.1, 0.2]}, "candidates": {"a": {"score": [0.5, 0.6]}}}
        cv["candidates"]["b"] = {"score": [0.9, 0.8]}
        rows = summarise(cv)
        assert [(r.setting, r.chosen) for r in rows] == [("b", True), ("a", False)]
        assert rows[0].mean == pytest.approx(0.85)
        assert rows[0].folds == 2

    def test_a_tie_keeps_the_order_the_log_printed(self) -> None:
        cv = {
            "folds": {"score": [0.5, 0.5, 0.5, 0.5]},
            "candidates": {"first": {"score": [0.5, 0.5]}, "second": {"score": [0.5, 0.5]}},
        }
        assert [r.setting for r in summarise(cv) if r.chosen] == ["first"]

    def test_one_setting_is_not_a_choice(self) -> None:
        cv = {"folds": {"score": [0.5, 0.6]}, "candidates": {"only": {"score": [0.5, 0.6]}}}
        assert [r.chosen for r in summarise(cv)] == [False]

    def test_one_stray_number_is_not_kept(self) -> None:
        assert record({"score": [0.9]}, {}) is None

    def test_a_single_fold_has_no_spread(self) -> None:
        cv = {"folds": {"score": [0.5, 0.6]}, "candidates": {"a": {"score": [0.5]}}}
        cv["candidates"]["b"] = {"score": [0.6]}
        assert all(r.std is None for r in summarise(cv))


class TestAGridSearch:
    def test_every_setting_is_kept_on_the_run(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, GRID)
        run = store.get_run(run_id)
        assert run is not None
        cv = run.config["cross_validation"]
        assert list(cv["candidates"]) == SETTINGS
        assert cv["candidates"][WINNER]["score"] == [0.94, 0.98, 0.96]

    def test_the_exports_name_the_setting_that_was_charted(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, GRID)
        charted = [e.value for e in store.get_metric_events(run_id)]
        assert charted == [pytest.approx(fmean([0.94, 0.98, 0.96]))]
        run = store.get_run(run_id)
        assert run is not None
        chosen = [r for r in summarise(run.config["cross_validation"]) if r.chosen]
        assert [r.setting for r in chosen] == [WINNER]
        assert chosen[0].mean == pytest.approx(charted[0])

    @pytest.mark.parametrize("locale", ["en", "fa", "fr"])
    def test_the_markdown_report_lists_every_setting(self, tmp_path: Path, locale: str) -> None:
        run_id, store = _parse(tmp_path, GRID, locale=locale)
        md = build_markdown(run_id=run_id, store=store)
        assert f"## {t('cv.search_title', locale)}" in md
        for setting in SETTINGS:
            assert f"`{setting}`" in md, setting
        assert f"`{WINNER}` ({t('cv.chosen', locale)})" in md
        assert md.count(f"({t('cv.chosen', locale)})") == 1

    def test_the_pdf_lists_every_setting(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, GRID)
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert t("cv.search_title", "en").encode() in text
        for setting in SETTINGS:
            assert setting.encode() in text, setting
        assert f"{WINNER}  ({t('cv.chosen', 'en')})".encode() in text

    def test_a_farsi_pdf_with_a_search_still_renders(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, GRID, locale="fa")
        assert build_pdf(run_id=run_id, store=store).startswith(b"%PDF")

    def test_the_json_export_carries_it(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, GRID)
        data = json.loads(build_json(run_id=run_id, store=store))
        assert list(data["run"]["config"]["cross_validation"]["candidates"]) == SETTINGS

    def test_check_names_the_same_winner(self, tmp_path: Path) -> None:
        log = tmp_path / "grid.log"
        log.write_text("\n".join(GRID) + "\n", encoding="utf-8")
        result = CliRunner().invoke(cli.app, ["check", str(log)])
        assert result.exit_code == 0, result.output
        charted = [ln for ln in result.output.splitlines() if "<- charted" in ln]
        assert len(charted) == 1 and WINNER in charted[0], result.output
        for setting in SETTINGS:
            assert setting in result.output


class TestAPlainCrossValidation:
    def test_the_folds_are_reported(self, tmp_path: Path) -> None:
        run_id, store = _parse(tmp_path, HANDWRITTEN)
        md = build_markdown(run_id=run_id, store=store)
        assert f"## {t('cv.title', 'en')}" in md
        assert t("cv.search_title", "en") not in md
        assert "| `accuracy` | 0.905 |" in md
        assert "0.8688 – 0.9375 | 5 |" in md

    def test_a_run_without_folds_has_no_section(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/3 train_loss={1 / e:.4f} val_accuracy={0.5 + 0.1 * e:.4f}"
            for e in (1, 2, 3)
        ]
        run_id, store = _parse(tmp_path, lines)
        run = store.get_run(run_id)
        assert run is not None
        assert "cross_validation" not in run.config
        assert t("cv.title", "en") not in build_markdown(run_id=run_id, store=store)
