"""The extension's HTTP calls must hit routes the server actually serves.

This exists because of a bug that survived every test: the VS Code extension
POSTed to ``/api/parse``, an endpoint that was never implemented. FastAPI
returned a 404 whose body — ``{"detail":"Not Found"}`` — is valid JSON, so the
client's ``JSON.parse`` succeeded, found no ``run_id``, and reported "could not
reach the Python engine". Every install silently fell back to the standalone
engine and lost saved run history.

The suite missed it because ``sidecarFallback.test.ts`` *mocks* ``parseLogFile``
— it asserted the fallback worked while stubbing out the exact call that was
broken. A green test for the degraded path is not evidence the primary path
works.

So this checks the contract itself: every URL literal in the extension's
sidecar client must correspond to a real route on the real app. It is the
cross-language version of the trap this project keeps hitting — two
implementations that drift because nothing compares them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from epochix.server.app import create_app

_VSCODE_SRC = Path(__file__).resolve().parents[2] / "epochix-vscode" / "src"

# Any `/api/...` string literal in the client — the path is built separately
# from the host, so matching on the host prefix would miss all of them.
_URL = re.compile(r"""["'`](/api/[^"'`\s?]*)["'`]""")

# A `${...}` interpolation inside a path is a path parameter; FastAPI spells
# those `{name}`, so normalise both sides before comparing.
_INTERP = re.compile(r"\$\{[^}]*\}")


def _normalise(path: str) -> str:
    return _INTERP.sub("{}", path).rstrip("/")


def _server_paths() -> set[str]:
    """Every /api path the real app serves.

    Read from the generated OpenAPI schema rather than by walking
    ``app.routes``. Current FastAPI keeps an included router as a nested
    ``_IncludedRouter`` whose children are not exposed as ``.routes``, so
    walking the route objects finds only the SPA handlers and would claim
    every API endpoint is missing. The schema is the app's own published
    contract and does not depend on those internals.
    """
    paths = create_app().openapi().get("paths", {})
    return {_normalise(re.sub(r"\{[^}]*\}", "{}", p)) for p in paths if str(p).startswith("/api")}


def _extension_paths() -> dict[str, str]:
    """Map each /api path the extension calls to the file it appears in."""
    found: dict[str, str] = {}
    for ts in _VSCODE_SRC.rglob("*.ts"):
        if ts.name.endswith(".test.ts"):
            continue
        for line in ts.read_text(encoding="utf-8").splitlines():
            # Skip comments — a docstring naming a dead endpoint is prose, not
            # a call, and flagging it would make this test cry wolf.
            stripped = line.lstrip()
            if stripped.startswith(("*", "//", "/*")):
                continue
            for match in _URL.finditer(line):
                found[_normalise(match.group(1))] = str(ts.relative_to(_VSCODE_SRC))
    return found


@pytest.mark.skipif(not _VSCODE_SRC.is_dir(), reason="extension source not present")
def test_every_endpoint_the_extension_calls_actually_exists() -> None:
    served = _server_paths()
    called = _extension_paths()

    assert called, "found no /api calls in the extension — has the URL shape changed?"

    missing = {path: where for path, where in called.items() if path not in served}
    assert not missing, (
        "The extension calls endpoints this server does not serve: "
        + ", ".join(f"{p} (in {w})" for p, w in sorted(missing.items()))
        + f". Server routes: {sorted(served)}"
    )


@pytest.mark.skipif(not _VSCODE_SRC.is_dir(), reason="extension source not present")
def test_the_endpoints_the_sidecar_client_depends_on_are_present() -> None:
    """Named explicitly, so deleting one on the Python side fails here rather
    than degrading silently in the extension."""
    served = _server_paths()
    for required in ("/api/runs", "/api/runs/{}/event", "/api/health"):
        assert required in served, f"{required} is gone; the extension depends on it"
