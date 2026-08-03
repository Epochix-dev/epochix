"""`__version__` must describe the code that is running.

`importlib.metadata.version("epochix")` reads the INSTALLED distribution's
metadata. On a machine with a release installed alongside a source checkout,
running from the checkout reported the installed number — `/api/version` said
0.5.75 while serving 0.5.80 source.

That drives a real decision: the VS Code extension compares `/api/version`
against its own version to warn about a stale Python package, so a wrong
answer here raises a false alarm or hides a real one.
"""

from __future__ import annotations

import re
from pathlib import Path

import epochix

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no [project] version in pyproject.toml"
    return match.group(1)


def test_version_matches_the_tree_when_running_from_source() -> None:
    """The suite runs against src/ (see pythonpath in pyproject).

    So the reported version must be the tree's, regardless of what version of
    epochix happens to be installed in site-packages on this machine.
    """
    running_from_tree = Path(epochix.__file__).resolve().is_relative_to(ROOT / "src")
    if not running_from_tree:  # pragma: no cover - installed-package CI variant
        return
    assert epochix.__version__ == _pyproject_version()


def test_version_is_never_the_unknown_placeholder_here() -> None:
    """`0.0.0+local` means neither metadata nor the tree could be read.

    In this repo one of them always can, so seeing it signals the resolution
    broke rather than that the package is merely uninstalled.
    """
    assert epochix.__version__ != "0.0.0+local"


def test_version_is_a_plain_release_number() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+([.\-+].+)?", epochix.__version__), epochix.__version__


def test_api_version_endpoint_reports_the_same_thing() -> None:
    """The endpoint the extension polls must agree with the package."""
    from fastapi.testclient import TestClient

    from epochix.config import Settings
    from epochix.server.app import create_app

    with TestClient(create_app(Settings(db=":memory:"))) as client:
        body = client.get("/api/version").json()
    assert body["version"] == epochix.__version__
