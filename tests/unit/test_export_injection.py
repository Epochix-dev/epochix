"""Exports must render untrusted input as text, not as markup.

A run name comes from a log file. That file is written by a training process,
which on a shared box, a cluster, or a downloaded repo is not necessarily
something the reader controls. The exports then travel: HTML opened in a
browser, Markdown pasted into a README, a VS Code preview, or Notion.

So the name is untrusted input crossing into three different renderers, each
with its own escape hatch:

* **HTML** — ``</script>`` ends the data island and the rest is executed.
* **Markdown** — ``[x](javascript:...)`` is a working link in every renderer
  that does not filter schemes, and raw HTML survives wherever it is allowed.
* **A table cell** — a bare ``|`` silently restructures the table.

None of these needs the name to be *long* or *weird*; it just has to contain
one character nobody escaped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.exporters import markdown_export
from epochix.exporters.markdown_export import _code_safe, _md_escape
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def _md(tmp_path: Path, name: str) -> str:
    log = tmp_path / "train.log"
    log.write_text(
        "".join(f"Epoch {i}/6 val_acc={0.30 + 0.1 * i:.4f}\n" for i in range(1, 7)),
        encoding="utf-8",
    )
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name=name)
    return markdown_export.build_markdown(run_id=run.id, store=RunStore(db_path=db))


@pytest.mark.parametrize(
    "payload",
    [
        "[click me](javascript:alert(1))",
        "![x](javascript:alert(1))",
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<iframe src=//evil.test>",
    ],
)
def test_a_run_name_cannot_smuggle_active_markup_into_markdown(
    payload: str, tmp_path: Path
) -> None:
    """The payload may still be *visible* — it is the run's name, after all.
    What it must not be is *active*: every character that would turn it into a
    link, an image or a tag has to arrive backslash-escaped.
    """
    title = next(line for line in _md(tmp_path, payload).splitlines() if line.startswith("# "))
    body = title[2:]
    for i, ch in enumerate(body):
        if ch in "[]()<>!`*_":
            assert i > 0 and body[i - 1] == "\\", f"unescaped {ch!r} in {body!r}"


def test_a_run_name_cannot_restructure_the_metrics_table(tmp_path: Path) -> None:
    """An unescaped pipe adds columns to a table the reader is trusting."""
    md = _md(tmp_path, "a | b | c")
    header_cols = md.count("| Field | Value |")
    assert header_cols == 1
    assert "\\|" in md or "| a | b | c |" not in md


def test_escaping_preserves_the_name_as_readable_text() -> None:
    """Escaping that mangles ordinary names is its own bug — most run names
    legitimately contain hyphens, underscores and dots."""
    out = _md_escape("resnet50_v2.1-baseline")
    assert out.replace("\\", "") == "resnet50_v2.1-baseline"


def test_a_backtick_cannot_escape_a_code_span() -> None:
    """Backslash escapes do not apply inside backticks — only another backtick
    closes the span, so dropping them is the only correct move."""
    assert "`" not in _code_safe("acc`</code><script>alert(1)</script>")


def test_control_characters_never_reach_the_document() -> None:
    for raw in ("a\x00b", "a\x1b[31mb", "a\x07b"):
        assert all(ch.isprintable() or ch in " \\" for ch in _md_escape(raw)), repr(raw)
