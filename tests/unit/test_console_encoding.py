"""The CLI must not die on a console that cannot encode a character.

A Windows console still defaults to cp1252. `epochix demo` — the first command
a newcomer runs, and the one the docs lead with — printed a raw "▶" and died
with UnicodeEncodeError before showing anything. Run names are worse: they are
user data, so no amount of transliterating *our* decorations can save them.

`PYTHONIOENCODING` reproduces that console on any OS, so these run in CI too.
"""

from __future__ import annotations

import io
import os
import pathlib
import socket
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from epochix.console import _for_windows_redirect, console_safe, console_symbols

if TYPE_CHECKING:
    from pathlib import Path


def _free_port() -> int:
    """Never use the default port: a developer machine (or another test) may
    already have an epochix server on it, and the run would fail for a reason
    that has nothing to do with what is being tested."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _cli(*args: str, db: Path, encoding: str = "cp1252") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "epochix", *args],
        capture_output=True,
        text=True,
        # Decode the child's output with the encoding the child used, not the
        # parent's locale — otherwise a UTF-8 child looks like mojibake here.
        encoding=encoding,
        timeout=300,
        env={
            **os.environ,
            "EPOCHIX_DB": str(db),
            "PYTHONIOENCODING": encoding,
            # See test_cli_export_and_port: a subprocess resolves
            # `epochix` from site-packages, not the working tree.
            "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[2] / "src"),
        },
        check=False,
    )


def _training_log(tmp_path: Path) -> Path:
    log = tmp_path / "train.log"
    log.write_text(
        "".join(
            f"Epoch {i}/3 train_loss={0.6 - i * 0.1:.4f} val_acc={0.70 + i * 0.05:.4f}\n"
            for i in range(1, 4)
        ),
        encoding="utf-8",
    )
    return log


@pytest.mark.parametrize("command", [("demo", "--headless"), ("list",)])
def test_commands_survive_a_legacy_console(command: tuple[str, ...], tmp_path: Path) -> None:
    extra = ("--port", str(_free_port())) if command[0] == "demo" else ()
    result = _cli(*command, *extra, db=tmp_path / "runs.db")
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_demo_still_announces_itself_without_the_glyph(tmp_path: Path) -> None:
    """Degrading must not mean printing nothing."""
    result = _cli("demo", "--headless", "--port", str(_free_port()), db=tmp_path / "runs.db")
    assert "Running bundled demo" in result.stdout, result.stdout


def test_a_run_name_the_console_cannot_encode(tmp_path: Path) -> None:
    """Run names are user data. epochix ships Persian localisation, so a
    Persian run name is an ordinary thing for a user to type."""
    db = tmp_path / "runs.db"
    run = _cli(
        "run",
        str(_training_log(tmp_path)),
        "--headless",
        "--name",
        "تجربه 🚀 run",
        "--port",
        str(_free_port()),
        db=db,
    )
    assert "UnicodeEncodeError" not in run.stderr, run.stderr
    assert run.returncode == 0, run.stderr

    listed = _cli("list", db=db)
    assert "UnicodeEncodeError" not in listed.stderr, listed.stderr
    assert listed.returncode == 0, listed.stderr


def test_utf8_console_keeps_the_real_glyphs(tmp_path: Path) -> None:
    """The fallback must not punish consoles that are perfectly capable."""
    result = _cli(
        "demo", "--headless", "--port", str(_free_port()), db=tmp_path / "runs.db", encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
    assert "▶" in result.stdout, result.stdout


# ── the helper itself ────────────────────────────────────────────────────────


def test_console_safe_passes_through_when_encodable() -> None:
    assert console_safe("plain ascii") == "plain ascii"


def test_console_safe_transliterates_when_it_must(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("epochix.console.console_can_encode", lambda _text: False)
    out = console_safe("▶ go → done …")
    assert "▶" not in out and "→" not in out and "…" not in out, out
    assert out.startswith(">"), out


def test_console_symbols_are_ascii_on_a_legacy_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("epochix.console.console_can_encode", lambda _text: False)
    assert console_symbols() == ("->", "OK", "!", "~")


# ── Windows output that is piped or redirected ──────────────────────────────
#
# Python writes a Windows pipe in the ANSI codepage while the reader decodes
# with its own, so `epochix demo | Out-File` garbled every "·" and "—". A
# redirect now gets UTF-8, with our own decorations as ASCII.


class _Pipe(io.TextIOWrapper):
    """What a redirected stdout is on Windows: cp1252, not a terminal."""

    def __init__(self) -> None:
        super().__init__(io.BytesIO(), encoding="cp1252", errors="replace")

    def isatty(self) -> bool:
        return False

    def written(self) -> bytes:
        self.flush()
        raw = self.buffer
        assert isinstance(raw, io.BytesIO)
        return raw.getvalue()


def _on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)


def test_a_windows_redirect_writes_utf8_with_ascii_decorations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _on_windows(monkeypatch)
    pipe = _Pipe()
    out = _for_windows_redirect(pipe)
    out.write("Demo · تجربه — ▶ → done…")
    # The user's Farsi survives; our decorations read in any codepage.
    assert pipe.written().decode("utf-8") == "Demo - تجربه - > -> done..."


def test_a_windows_redirect_is_wrapped_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _on_windows(monkeypatch)
    once = _for_windows_redirect(_Pipe())
    assert _for_windows_redirect(once) is once


@pytest.mark.parametrize("variable", ["PYTHONIOENCODING", "PYTHONUTF8"])
def test_an_encoding_the_user_chose_wins(variable: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _on_windows(monkeypatch)
    monkeypatch.setenv(variable, "utf-8" if variable == "PYTHONIOENCODING" else "1")
    pipe = _Pipe()
    assert _for_windows_redirect(pipe) is pipe


def test_a_terminal_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _on_windows(monkeypatch)
    pipe = _Pipe()
    monkeypatch.setattr(pipe, "isatty", lambda: True)
    assert _for_windows_redirect(pipe) is pipe


def test_other_platforms_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    pipe = _Pipe()
    assert _for_windows_redirect(pipe) is pipe


@pytest.mark.skipif(sys.platform != "win32", reason="the ANSI-codepage pipe is Windows-only")
def test_piped_demo_on_windows_is_utf8(tmp_path: Path) -> None:
    """The real journey: the CLI's stdout is a pipe, nothing chosen by the user."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["EPOCHIX_DB"] = str(tmp_path / "runs.db")
    env["PYTHONPATH"] = str(pathlib.Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "epochix",
            "run",
            str(_training_log(tmp_path)),
            "--headless",
            "--name",
            "تجربه · run",
            "--port",
            str(_free_port()),
        ],
        capture_output=True,
        timeout=300,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    stdout = result.stdout.decode("utf-8")  # raises if it is not UTF-8
    assert "تجربه - run" in stdout, stdout
    assert "·" not in stdout and "—" not in stdout, stdout
