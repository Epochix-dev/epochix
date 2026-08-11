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
import sys

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
