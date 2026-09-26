"""A comparison of runs can leave the browser.

The comparison view overlays the curves and explains the difference in a
paragraph; the race GIF could carry the curves out, and nothing could carry
the explanation or the numbers behind it. ``epochix compare``, the
``/api/export/compare/md`` endpoint and the view's download button now write
it as Markdown — the same narrative, with each run's grade, final and best.

Driven end to end: real logs through ``parse()`` into one database, then the
CLI, the API and the exporter against it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import epochix.cli as cli
from epochix import parse
from epochix.config import Settings
from epochix.exporters.compare_export import build_comparison_markdown
from epochix.i18n import t
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def _log(accs: list[float]) -> list[str]:
    n = len(accs)
    return [
        f"Epoch {e}/{n} train_loss={1.0 / e:.4f} val_accuracy={a:.4f}"
        for e, a in enumerate(accs, 1)
    ]


STRONG = [0.60, 0.72, 0.80, 0.86, 0.90, 0.92]
WEAK = [0.50, 0.55, 0.58, 0.60, 0.61, 0.62]


def _run(tmp_path: Path, db: Path, name: str, lines: list[str], locale: str = "en") -> str:
    log = tmp_path / f"{name}-{len(lines)}-{locale}.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return parse(log, db=str(db), run_name=name, locale=locale).id


@pytest.fixture()
def two_runs(tmp_path: Path) -> tuple[Path, str, str]:
    db = tmp_path / "runs.db"
    return db, _run(tmp_path, db, "strong", _log(STRONG)), _run(tmp_path, db, "weak", _log(WEAK))


class TestTheDocument:
    def test_it_says_who_won_and_shows_each_runs_numbers(
        self, two_runs: tuple[Path, str, str]
    ) -> None:
        db, a, b = two_runs
        md = build_comparison_markdown([a, b], RunStore(db_path=str(db)))
        assert md.startswith(f"# {t('cmp.title', 'en')}")
        assert "strong finished ahead of weak" in md
        rows = [
            ln for ln in md.splitlines() if ln.startswith("| strong") or ln.startswith("| weak")
        ]
        assert len(rows) == 2, md
        assert "0.92" in rows[0] and "0.92 (epoch 6)" in rows[0]
        assert "0.62" in rows[1] and "| 6 |" in rows[1]
        assert a in md and b in md

    def test_runs_on_different_metrics_are_refused_not_ranked(self, tmp_path: Path) -> None:
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "acc", _log(STRONG))
        loss = [f"Epoch {e}/6 train_loss={1.0 / e:.4f}" for e in range(1, 7)]
        b = _run(tmp_path, db, "loss", loss)
        md = build_comparison_markdown([a, b], RunStore(db_path=str(db)))
        assert "not comparable" in md
        assert "finished ahead" not in md

    def test_two_runs_with_one_name_are_told_apart(self, tmp_path: Path) -> None:
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "same", _log(STRONG))
        b = _run(tmp_path, db, "same", _log(WEAK))
        md = build_comparison_markdown([a, b], RunStore(db_path=str(db)))
        assert f"same ({a[-4:]})" in md and f"same ({b[-4:]})" in md

    def test_it_is_told_in_the_runs_language(self, tmp_path: Path) -> None:
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "a", _log(STRONG), locale="fa")
        b = _run(tmp_path, db, "b", _log(WEAK), locale="fa")
        md = build_comparison_markdown([a, b], RunStore(db_path=str(db)))
        assert md.startswith(f"# {t('cmp.title', 'fa')}")
        assert "finished ahead" not in md

    def test_fewer_than_two_runs_or_an_unknown_one_is_an_error(
        self, two_runs: tuple[Path, str, str]
    ) -> None:
        db, a, _ = two_runs
        store = RunStore(db_path=str(db))
        with pytest.raises(ValueError, match="at least two"):
            build_comparison_markdown([a], store)
        with pytest.raises(ValueError, match="not found"):
            build_comparison_markdown([a, "ghost"], store)


class TestTheSurfaces:
    def test_the_cli_writes_it(
        self, two_runs: tuple[Path, str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, a, b = two_runs
        monkeypatch.setenv("EPOCHIX_DB", str(db))
        out = tmp_path / "cmp.md"
        result = CliRunner().invoke(cli.app, ["compare", a, b, "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert "strong finished ahead of weak" in out.read_text(encoding="utf-8")

        printed = CliRunner().invoke(cli.app, ["compare", a, b])
        assert printed.exit_code == 0 and "strong finished ahead of weak" in printed.output

        bad = CliRunner().invoke(cli.app, ["compare", a, "ghost"])
        assert bad.exit_code == 1

    def test_the_api_serves_it_as_a_download(self, two_runs: tuple[Path, str, str]) -> None:
        db, a, b = two_runs
        with TestClient(create_app(Settings(db=str(db)))) as client:
            r = client.get(f"/api/export/compare/md?runs={a},{b}")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("text/markdown")
            assert "attachment" in r.headers["content-disposition"]
            assert "strong finished ahead of weak" in r.text
            assert client.get(f"/api/export/compare/md?runs={a},ghost").status_code == 404
            assert client.get(f"/api/export/compare/md?runs={a}").status_code == 400

    def test_the_comparison_view_narrative_is_in_the_runs_language(self, tmp_path: Path) -> None:
        """It was English whatever language the runs were narrated in."""
        db = tmp_path / "runs.db"
        a = _run(tmp_path, db, "a", _log(STRONG), locale="fr")
        b = _run(tmp_path, db, "b", _log(WEAK), locale="fr")
        with TestClient(create_app(Settings(db=str(db)))) as client:
            narrative = client.get(f"/api/compare?run_ids={a},{b}").json()["narrative"]
        assert narrative
        assert "finished ahead" not in narrative
