"""Printing that survives a legacy console.

A Windows console still defaults to cp1252, which cannot encode the box and
arrow characters we decorate output with. Printing one raises
``UnicodeEncodeError`` and kills the command outright — which is what
``epochix demo``, the first thing a newcomer runs, did on Windows.

Route any user-facing string containing a decoration through
:func:`console_safe`.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterable
from typing import TextIO, cast

# Decorations we print, and what to say instead when the console cannot encode
# them.
_ASCII_FALLBACKS = {
    "→": "->",  # arrow
    "✓": "OK",  # tick
    "✗": "!",  # cross
    "⟳": "~",  # spinner
    "▶": ">",  # play
    "…": "...",  # ellipsis
    "—": "-",  # em dash
    "•": "*",  # bullet
    "⚠": "!",  # warning
    "·": "-",  # middle dot ("Demo · keras_image_classifier.log")
}


def console_can_encode(text: str) -> bool:
    """True if ``text`` can be written to stdout without raising."""
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def transliterate(text: str) -> str:
    """Replace known decorations with ASCII, ALWAYS.

    ``console_safe`` applies this only when the console cannot encode the
    text, which is right for a terminal and wrong for anything with a fixed
    character set. The PDF exporter renders with Latin-1 core fonts, so on a
    UTF-8 terminal every em dash reached it untouched and became "?" —
    "63.5% accuracy ? only one direction from here".
    """
    for uni, plain in _ASCII_FALLBACKS.items():
        text = text.replace(uni, plain)
    return text


def console_safe(text: str) -> str:
    """Make ``text`` printable on this console instead of crashing on it.

    Known decorations are transliterated; anything still unencodable is
    replaced rather than allowed to raise.
    """
    if console_can_encode(text):
        return text
    text = transliterate(text)
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def console_symbols() -> tuple[str, str, str, str]:
    """``(arrow, tick, cross, spinner)`` — ASCII fallbacks on legacy consoles."""
    if console_can_encode("→✓✗⟳"):
        return "→", "✓", "✗", "⟳"
    return "->", "OK", "!", "~"


def harden_streams() -> None:
    """Stop an unencodable character from ever killing a command.

    Run names, log paths and narratives are user data and can contain anything
    — a Persian run name crashed both ``epochix run --name`` and ``epochix
    list`` on a cp1252 console. Transliterating our own decorations
    (:func:`console_safe`) cannot help there, because we do not control the
    text. Replacing on encode does: the character renders as ``?`` instead of
    aborting the run.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (pytest capture, a pipe wrapper)
        # A closed or detached stream is not worth failing the command over.
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="replace")
    sys.stdout = _for_windows_redirect(sys.stdout)
    sys.stderr = _for_windows_redirect(sys.stderr)


def _for_windows_redirect(stream: TextIO) -> TextIO:
    """UTF-8 with ASCII decorations when Windows output is piped or redirected.

    Python writes a Windows pipe in the ANSI codepage (cp1252), while whatever
    reads it decodes with its own: ``epochix demo | Out-File`` garbled every
    middle dot and em dash, written in one codepage and read in another. So a
    redirect gets UTF-8,
    which keeps user data (a Farsi run name) correct for any reader that
    speaks it, and our own decorations as ASCII, which read cleanly in any
    codepage. A terminal is left alone (Python talks to it in Unicode), and so
    is an encoding the user chose with PYTHONIOENCODING or PYTHONUTF8.
    """
    if (
        isinstance(stream, _AsciiDecorations)
        or sys.platform != "win32"
        or os.environ.get("PYTHONIOENCODING")
        or os.environ.get("PYTHONUTF8")
    ):
        return stream
    try:
        if stream.isatty():
            return stream
    except (AttributeError, ValueError, OSError):
        return stream  # closed, detached, or not a real stream
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return stream
    with contextlib.suppress(ValueError, OSError):
        reconfigure(encoding="utf-8", errors="replace")
    return cast(TextIO, _AsciiDecorations(stream))


class _AsciiDecorations:
    """A text stream that writes our own decorations as ASCII; else delegates."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, s: str) -> int:
        return self._stream.write(transliterate(s))

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self._stream.fileno()

    @property
    def encoding(self) -> str:
        return self._stream.encoding

    @property
    def buffer(self) -> object:
        return self._stream.buffer

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)
