"""`epochix check` — the self-diagnosis path.

An AI agent asked to use the library resorted to `inspect.getsource()` on our
internals to work out what log format we accept, because nothing told it. This
command is the answer: point it at a log and it reports what was parsed and
what to add.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from epochix.cli import _subcommand_names, app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_HEALTHY = """\
Model: "sequential"
_________________________________________________________________
 Layer (type)                Output Shape              Param #
=================================================================
 conv2d (Conv2D)             (None, 30, 30, 32)        896
 dense (Dense)               (None, 10)                650
=================================================================
Total params: 1,546
Epoch 1/3
100/100 [==============================] - 2s - loss: 0.9 - val_accuracy: 0.62
Epoch 2/3
100/100 [==============================] - 2s - loss: 0.6 - val_accuracy: 0.79
Epoch 3/3
100/100 [==============================] - 2s - loss: 0.4 - val_accuracy: 0.88
"""

_LOSS_ONLY = "\n".join(
    f"Epoch {e}/5 train_loss={0.5 - e * 0.05:.4f} val_loss={0.45 - e * 0.04:.4f}"
    for e in range(1, 6)
)


def test_check_is_a_real_subcommand() -> None:
    """The router used a hardcoded command list; a new command was unreachable."""
    assert "check" in _subcommand_names()


def test_check_reports_a_healthy_log(tmp_path: Path) -> None:
    log = tmp_path / "good.log"
    log.write_text(_HEALTHY, encoding="utf-8")

    result = runner.invoke(app, ["check", str(log)])
    assert result.exit_code == 0, result.output
    assert "keras" in result.output
    assert "classification" in result.output
    assert "val_accuracy" in result.output
    assert "everything epochix needs is present" in result.output


def test_check_names_what_is_missing(tmp_path: Path) -> None:
    """A loss-only log: say why the grade is loss-based and the panel empty."""
    log = tmp_path / "loss.log"
    log.write_text(_LOSS_ONLY, encoding="utf-8")

    result = runner.invoke(app, ["check", str(log)])
    assert result.exit_code == 0, result.output
    assert "val_loss" in result.output
    # Both gaps, each with a concrete fix.
    assert "No task-defining metric" in result.output
    assert "val_accuracy=" in result.output  # the suggested print line
    assert "No model architecture" in result.output
    assert "LiveReporter(model=model)" in result.output


def test_check_handles_an_unparseable_log(tmp_path: Path) -> None:
    log = tmp_path / "junk.log"
    log.write_text("hello world\nnothing here\n", encoding="utf-8")

    result = runner.invoke(app, ["check", str(log)])
    assert result.exit_code == 0, result.output
    assert "No metrics were recognised" in result.output


def test_console_symbols_fall_back_on_a_legacy_encoding(monkeypatch) -> None:
    """A Windows console reports cp1252, which cannot encode "→"/"✓"."""
    import sys as _sys

    from epochix import cli

    class _Cp1252Stream:
        encoding = "cp1252"

    monkeypatch.setattr(_sys, "stdout", _Cp1252Stream())
    assert cli.console_symbols() == ("->", "OK", "!", "~")


def test_check_output_is_ascii_safe_on_a_legacy_console(tmp_path: Path, monkeypatch) -> None:
    """With ASCII symbols selected, every remaining literal must encode too.

    The first version printed "…" and "—" inside the advice text, which crashed
    on cp1252 even once the symbols themselves were ASCII.
    """
    from epochix import cli

    monkeypatch.setattr(cli, "console_symbols", lambda: ("->", "OK", "!", "~"))

    log = tmp_path / "loss.log"
    log.write_text(_LOSS_ONLY, encoding="utf-8")
    result = runner.invoke(app, ["check", str(log)])

    assert result.exit_code == 0, result.output
    result.output.encode("cp1252")  # raises UnicodeEncodeError if we regress


def test_check_rejects_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path / "nope.log")])
    assert result.exit_code == 1
