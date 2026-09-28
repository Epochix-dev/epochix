"""The comparison as a PDF: the narrative, the curves overlaid, the table.

The Markdown comparison (0.7.16) carried the explanation and each run's
numbers but no curve; the race GIF carried curves and no explanation. The PDF
has both, built from the same Comparison as the Markdown, so the two cannot
disagree. Driven end to end: real logs through parse(), then the exporter, the
CLI and the API.
"""

from __future__ import annotations

import re
import zlib
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import epochix.cli as cli
from epochix import parse
from epochix.config import Settings
from epochix.exporters import _pdf_render
from epochix.exporters.compare_export import build_comparison_pdf
from epochix.i18n import t
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

STRONG = [0.60, 0.72, 0.80, 0.86, 0.90, 0.92]
WEAK = [0.50, 0.55, 0.58, 0.60, 0.61, 0.62]


def _acc_log(accs: list[float]) -> list[str]:
    n = len(accs)
    return [
        f"Epoch {e}/{n} train_loss={1.0 / e:.4f} val_accuracy={a:.4f}"
        for e, a in enumerate(accs, 1)
    ]


def _run(tmp_path: Path, db: Path, name: str, lines: list[str], locale: str = "en") -> str:
    log = tmp_path / f"{name}-{locale}.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return parse(log, db=str(db), run_name=name, locale=locale).id


def _pages(pdf: bytes) -> list[bytes]:
    """Each page's decompressed content stream, in order."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            blob = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        if b"BT" in blob or b" l" in blob:
            out.append(blob)
    return out


def _text(blob: bytes) -> bytes:
    joined = b" ".join(re.findall(rb"\((.*?)\) ?Tj", blob))
    return joined.replace(b"\\(", b"(").replace(b"\\)", b")")


def _segments(blob: bytes) -> int:
    """Stroked line segments — the curves (and gridlines) on a page."""
    return len(re.findall(rb"\sl\s", blob))


@pytest.fixture()
def two_runs(tmp_path: Path) -> tuple[Path, str, str]:
    db = tmp_path / "runs.db"
    a = _run(tmp_path, db, "strong", _acc_log(STRONG))
    b = _run(tmp_path, db, "weak", _acc_log(WEAK))
    return db, a, b


class TestTheDocument:
    def test_it_carries_the_narrative_the_curves_and_the_table(
        self, two_runs: tuple[Path, str, str]
    ) -> None:
        db, a, b = two_runs
        pages = _pages(build_comparison_pdf([a, b], RunStore(db_path=str(db))))
        assert len(pages) == 2, len(pages)
        first, table = _text(pages[0]), _text(pages[1])
        assert t("cmp.title", "en").encode() in first
        assert b"strong finished ahead of weak" in first
        # Two runs of six epochs each: at least ten curve segments, plus grid.
        assert _segments(pages[0]) >= 10
        for label in (b"strong", b"weak"):
            assert label in first  # the chart's legend
            assert label in table
        assert b"0.92 (epoch 6)" in table
        assert a.encode() in table and b.encode() in table

    def test_runs_on_different_metrics_are_not_overlaid(self, tmp_path: Path) -> None:
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "acc", _acc_log(STRONG))
        b = _run(
            tmp_path, db, "loss", [f"Epoch {e}/6 train_loss={1.0 / e:.4f}" for e in range(1, 7)]
        )
        pages = _pages(build_comparison_pdf([a, b], RunStore(db_path=str(db))))
        assert b"not comparable" in _text(pages[0])
        # No chart: a chart would rank them by eye after the text refused to.
        assert _segments(pages[0]) == 0

    def test_a_farsi_comparison_is_drawn_in_farsi(self, tmp_path: Path) -> None:
        pytest.importorskip("uharfbuzz")
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "a", _acc_log(STRONG), locale="fa")
        b = _run(tmp_path, db, "b", _acc_log(WEAK), locale="fa")
        pdf = build_comparison_pdf([a, b], RunStore(db_path=str(db)))
        assert b"Vazirmatn" in pdf, "the Persian font was not embedded"
        assert _pdf_render._UNRENDERABLE_NOTE.encode() not in pdf

    def test_without_the_shaper_it_falls_back_to_english_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_pdf_render, "can_draw_persian", lambda: False)
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "a", _acc_log(STRONG), locale="fa")
        b = _run(tmp_path, db, "b", _acc_log(WEAK), locale="fa")
        pdf = build_comparison_pdf([a, b], RunStore(db_path=str(db)))
        first = b" ".join(re.findall(rb"\((.*?)\) ?Tj", _pages(pdf)[0]))
        assert t("cmp.title", "en").encode() in first
        assert b"a finished ahead of b" in first
        assert b"pdf extra" in first.lower() or b"epochix[pdf]" in first
        assert b"?????" not in first


class TestTheSurfaces:
    def test_the_cli_writes_a_pdf(
        self, two_runs: tuple[Path, str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, a, b = two_runs
        monkeypatch.setenv("EPOCHIX_DB", str(db))
        out = tmp_path / "cmp.pdf"
        result = CliRunner().invoke(cli.app, ["compare", a, b, "-f", "pdf", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_bytes().startswith(b"%PDF")
        bad = CliRunner().invoke(cli.app, ["compare", a, b, "-f", "docx"])
        assert bad.exit_code == 1

    def test_the_api_serves_a_pdf(self, two_runs: tuple[Path, str, str]) -> None:
        db, a, b = two_runs
        with TestClient(create_app(Settings(db=str(db)))) as client:
            r = client.get(f"/api/export/compare/pdf?runs={a},{b}")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf"
            assert "attachment" in r.headers["content-disposition"]
            assert r.content.startswith(b"%PDF")
            assert client.get(f"/api/export/compare/pdf?runs={a},ghost").status_code == 404
            assert client.get(f"/api/export/compare/pdf?runs={a}").status_code == 400
