"""Sanitise untrusted values before they reach a log line.

A run id arrives from the URL path, and a run name arrives from a log file.
Neither is guaranteed to be a single line. Written into a log verbatim, a value
containing a newline forges entries::

    run_id=abc
    2026-08-02 12:00:00 ERROR  auth: admin login from 10.0.0.1

Anyone reading the log — or any tool parsing it — sees the second line as real.
The same applies to carriage returns (which overwrite the line on a terminal)
and to ANSI escapes, which can colour a forged line to match.

This is the log-facing sibling of the filename sanitiser in ``routes_export``:
same untrusted values, different sink, so it is written where it is used rather
than assumed to have been validated upstream.
"""

from __future__ import annotations

import re

# Anything outside printable ASCII-plus-common-Unicode that could break a line
# or drive a terminal. Newline, carriage return, tab, and the C0/C1 control
# ranges including ESC (which starts an ANSI sequence).
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

_MAX_LOGGED_CHARS = 200


def log_safe(value: object) -> str:
    """Return *value* as a single-line string that cannot forge a log entry.

    Control characters become ``?`` rather than being dropped, so a tampered
    value still looks tampered with instead of silently reading as clean.
    """
    text = _CONTROL.sub("?", str(value))
    if len(text) > _MAX_LOGGED_CHARS:
        text = text[: _MAX_LOGGED_CHARS - 1] + "…"
    return text
