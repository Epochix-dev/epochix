"""Security properties of the source itself, and of the one guard that is easy
to delete by accident.

These exist because both findings came from a scanner rather than from a
failing test — which means nothing in the suite would have noticed either one
appearing, or reappearing.
"""

from __future__ import annotations

import io
import tokenize
import unicodedata
from pathlib import Path

import pytest

from epochix.parsers.llm_fallback import _checked_request

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "epochix"

# Bidi overrides matter wherever text is *read*, not just where it is executed.
# README.md and CHANGELOG.md are rendered on PyPI and GitHub, and the docs are
# published to epochix.dev — a reversed line there misleads exactly as well as
# one in a .py file. Added after a stray U+0001 reached CHANGELOG.md through an
# unescaped `\1` in a build script, which the source-only scan did not watch.
_PROSE = ["README.md", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md"]

# The frontend and the extension were never scanned, only src/epochix. A shell
# heredoc turned `- ` into LITERAL control characters inside a regex
# in frontend/src/escape.js — it still worked, which is exactly why nothing
# would have caught it. Same failure family as the U+202E in gif_export.py.
_JS_ROOTS = [ROOT / "frontend" / "src", ROOT / "epochix-vscode" / "src"]
_JS_SUFFIXES = {".js", ".ts", ".mjs", ".css"}


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


def test_no_control_characters_in_frontend_or_extension_source() -> None:
    """Same rule, the other half of the codebase.

    Tab is allowed (real indentation); everything else below U+0020 apart from
    the line break is a character that got there by accident and will not
    survive review, because nobody can see it.
    """
    offenders: list[str] = []
    for root in _JS_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            parts = set(path.parts)
            # Test files are exempt: a test for ANSI stripping has to contain
            # real ESC bytes, and terminalJourney.test.ts legitimately does.
            # The hazard is an invisible character in SHIPPED code, where no
            # reviewer can see it.
            if (
                path.suffix not in _JS_SUFFIXES
                or "node_modules" in parts
                or {"test", "tests", "__tests__"} & parts
                or ".test." in path.name
                or ".spec." in path.name
            ):
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for ch in line:
                    if ch != "\t" and unicodedata.category(ch) in {"Cc", "Cf"}:
                        offenders.append(f"{path.relative_to(ROOT)}:{i} U+{ord(ch):04X}")
    assert not offenders, f"control characters in frontend/extension source: {offenders}"


def test_no_control_characters_in_published_prose() -> None:
    """The files that get rendered on PyPI, GitHub and the docs site.

    Same reasoning as the source scan: a bidi override reverses what a reader
    sees. Tab and newline are the only control characters legitimately present.
    """
    offenders = []
    for name in _PROSE:
        path = ROOT / name
        if not path.is_file():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ch in line:
                if ch != "\t" and (unicodedata.category(ch) in {"Cc", "Cf"}):
                    offenders.append(f"{name}:{i} U+{ord(ch):04X}")
    assert not offenders, f"control characters in published prose: {offenders}"


def test_no_unassigned_format_characters_in_source() -> None:
    """Catch the wider class, not just the nine codepoints named above.

    Any Cf (format) character is invisible and can hide or reorder text. Code
    has no reason to contain one — but *Persian* does: `دوره‌ها` needs a ZERO
    WIDTH NON-JOINER between its letters or they join and the word is
    misspelled. The i18n table is full of them.

    So the ban is enforced on code and relaxed for string literals, and only
    for the two joiners. A joiner cannot reorder anything; the bidi overrides
    and isolates that make Trojan Source work stay banned everywhere, literals
    included.
    """
    allowed_in_literals = {"‌", "‍"}  # ZWNJ, ZWJ — Persian orthography

    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        literal_spans: set[tuple[int, int]] = set()
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.STRING:
                    for row in range(tok.start[0], tok.end[0] + 1):
                        literal_spans.add((row, tok.start[1] if row == tok.start[0] else 0))
        except (tokenize.TokenError, IndentationError):  # pragma: no cover
            literal_spans = set()

        literal_rows = {row for row, _ in literal_spans}
        for i, line in enumerate(source.splitlines(), 1):
            for ch in line:
                if unicodedata.category(ch) != "Cf":
                    continue
                if ch in allowed_in_literals and i in literal_rows:
                    continue
                offenders.append(f"{path.relative_to(SRC)}:{i} U+{ord(ch):04X}")

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
