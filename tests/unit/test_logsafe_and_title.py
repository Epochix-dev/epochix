"""Untrusted values reaching a log line and the exported HTML <title>.

Both come from the same place — a run id in the URL, a run name in a log file
— and both were sinks that trusted the value to have been cleaned somewhere
upstream. Neither had a test.
"""

from __future__ import annotations

import re

import pytest

from epochix.exporters.html_export import _esc
from epochix.server.logsafe import log_safe


@pytest.mark.parametrize(
    "evil",
    [
        "abc\n2026-08-02 12:00:00 ERROR auth: admin login from 10.0.0.1",
        "abc\r\nFAKE ENTRY",
        "abc\roverwrite",
        "run\x1b[31mred",  # ANSI: colours a forged line to match the real ones
        "run\x00null",
    ],
)
def test_log_safe_cannot_forge_a_second_line(evil: str) -> None:
    out = log_safe(evil)
    assert "\n" not in out
    assert "\r" not in out
    assert "\x1b" not in out
    assert "\x00" not in out


def test_log_safe_marks_tampering_rather_than_hiding_it() -> None:
    """Control characters become '?' instead of vanishing.

    A value that was tampered with should still look tampered with; silently
    dropping the bytes makes a forged id read as a clean one.
    """
    assert log_safe("a\nb") == "a?b"


def test_log_safe_caps_length() -> None:
    assert len(log_safe("x" * 5000)) <= 200


def test_log_safe_leaves_ordinary_ids_alone() -> None:
    assert log_safe("01JQZ8YB4K7N2M") == "01JQZ8YB4K7N2M"


@pytest.mark.parametrize("name", [r"run\1", r"run\g<0>", "run\\", r"a\g<name>b"])
def test_export_title_survives_regex_metacharacters_in_a_run_name(name: str) -> None:
    """A run name is not a regex replacement template.

    ``re.sub`` with a *string* replacement expands backslash escapes in it, so
    a run named ``run\\1`` raised ``re.error`` and turned the HTML export into
    a 500. Run names come from log files, so this was reachable by naming a
    run. The fix is a function replacement, which is inserted literally.
    """
    title = _esc(f"{name} — Epochix")
    out = re.sub(
        r"<title>.*?</title>",
        lambda _m: f"<title>{title}</title>",
        "<head><title>placeholder</title></head>",
        count=1,
        flags=re.S,
    )
    assert "placeholder" not in out
    assert out.count("<title>") == 1


def test_export_title_escapes_markup() -> None:
    assert _esc('x"><script>alert(1)</script>') == (
        "x&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
    )


def test_export_title_escapes_single_quotes_too() -> None:
    """html.escape(quote=True) covers ' as well — the hand-rolled version did not."""
    assert "'" not in _esc("it's")
