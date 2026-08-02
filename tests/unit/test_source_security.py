"""Security properties of the source itself, and of the one guard that is easy
to delete by accident.

These exist because both findings came from a scanner rather than from a
failing test — which means nothing in the suite would have noticed either one
appearing, or reappearing.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from epochix.parsers.llm_fallback import _checked_request

SRC = Path(__file__).resolve().parents[1] / "src" / "epochix"


def test_no_bidi_control_characters_in_source() -> None:
    """No source file may contain a bidirectional override.

    U+202E and friends reorder how text *displays* without changing what the
    interpreter runs, so a reviewer reading the diff and the machine executing
    it can disagree. The docstring in gif_export.py that explains this attack
    contained a live instance of it.
    """
    bidi = {
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
    offenders = [
        f"{path.relative_to(SRC)}:{i}"
        for path in SRC.rglob("*.py")
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if bidi & set(line)
    ]
    assert not offenders, f"bidirectional control characters in source: {offenders}"


def test_no_unassigned_format_characters_in_source() -> None:
    """Catch the wider class, not just the nine codepoints named above.

    Any Cf (format) character is invisible and can hide or reorder text. The
    only ones a Python source file has a legitimate reason to contain are none.
    """
    offenders = [
        f"{path.relative_to(SRC)}:{i}"
        for path in SRC.rglob("*.py")
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(unicodedata.category(ch) == "Cf" for ch in line)
    ]
    assert not offenders, f"invisible format characters in source: {offenders}"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://C:/Windows/win.ini",
        "gopher://attacker/",
        "ftp://host/file",
        "data:text/plain,x",
        "",
        "/no/scheme/at/all",
    ],
)
def test_llm_endpoint_rejects_non_http_schemes(url: str) -> None:
    """EPOCHIX_LLM_URL is user-set and urlopen honours file://.

    Without this guard, a typo or a hostile config turns "call my local model"
    into "read this path off disk and feed it to a prompt".
    """
    with pytest.raises(ValueError, match="http or https"):
        _checked_request(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/api/generate",
        "https://api.openai.com/v1/chat/completions",
        "HTTP://Ollama.local:11434/api/generate",  # scheme compare is case-insensitive
    ],
)
def test_llm_endpoint_accepts_real_endpoints(url: str) -> None:
    assert _checked_request(url) == url
