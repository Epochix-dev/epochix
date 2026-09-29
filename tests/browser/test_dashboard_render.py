"""Cross-browser rendering tests for the live dashboard.

These launch a real uvicorn server over a real parsed run and drive the actual
dashboard in Chromium, Firefox and WebKit (Safari's engine). They catch what
the Python and vitest suites cannot: a canvas that never paints, a JS bundle
feature an engine doesn't support, a layout that collapses to zero width.

Not part of the default `pytest tests/unit tests/integration` run — they need
the built frontend bundle plus `playwright install`. CI runs them in their own
job (see the `browser` job in .github/workflows/ci.yml).
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import uvicorn

from epochix import parse
from epochix.config import Settings
from epochix.server.app import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

# The bundle the server serves; built by `npm --prefix frontend run build` and
# copied into the package. Without it the server is API-only and there is
# nothing to render.
_FRONTEND_INDEX = (
    Path(__file__).parents[2] / "src" / "epochix" / "_frontend" / "dist" / "index.html"
)

_LOG = Path(__file__).parents[1] / "fixtures" / "logs" / "keras_50ep.log"

BROWSERS = ["chromium", "firefox", "webkit"]

# In CI every engine must actually run. Locally a missing/broken engine (e.g.
# Playwright's Firefox cannot spawn on some Windows setups) skips instead of
# failing, so the suite stays usable on a dev box.
_REQUIRE_ALL = os.environ.get("EPOCHIX_REQUIRE_ALL_BROWSERS") == "1"

# Panels that must be on screen for a keras classification run.
_MIN_VISIBLE_CANVASES = 4


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def dashboard(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str]]:
    """Parse a real log, serve it, and yield (base_url, run_id)."""
    if not _FRONTEND_INDEX.is_file():
        # Skipping here would skip EVERY browser test, and an all-skipped run
        # still exits 0 — CI would go green having rendered nothing. Under
        # EPOCHIX_REQUIRE_ALL_BROWSERS a missing bundle is a hard failure.
        msg = (
            "frontend bundle not built — run `npm --prefix frontend run build` and copy "
            f"the output to {_FRONTEND_INDEX.parent}"
        )
        if _REQUIRE_ALL:
            pytest.fail(msg)
        pytest.skip(msg)

    db_path = str(tmp_path_factory.mktemp("browser") / "runs.db")
    run = parse(_LOG, db=db_path, run_name="browser/keras_50ep")
    assert run.id

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings=Settings(db=db_path)),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start within 30s")
        time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{port}", run.id
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_dashboard_renders_without_errors(
    dashboard: tuple[str, str],
    browser_name: str,
) -> None:
    """The dashboard paints its canvases and logs no JS errors, on every engine."""
    base_url, run_id = dashboard
    console_errors: list[str] = []

    with sync_playwright() as pw:
        browser_type = getattr(pw, browser_name)
        try:
            browser = browser_type.launch()
        except Exception as exc:  # noqa: BLE001 — engine unavailable, not an app bug
            if _REQUIRE_ALL:
                pytest.fail(f"{browser_name} failed to launch: {exc}")
            pytest.skip(f"{browser_name} unavailable on this host: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on(
                "console",
                lambda msg: (
                    console_errors.append(f"console.{msg.type}: {msg.text}")
                    if msg.type == "error"
                    else None
                ),
            )
            page.on("pageerror", lambda err: console_errors.append(f"pageerror: {err}"))

            page.goto(f"{base_url}/v/{run_id}", wait_until="networkidle")
            # The canvases paint on requestAnimationFrame; give the loop time to
            # size its buffers and draw at least one real frame.
            page.wait_for_timeout(3000)

            canvases = page.evaluate(
                """() => [...document.querySelectorAll('canvas')]
                    .filter(c => c.offsetParent !== null)
                    .map(c => ({ id: c.id || c.className, w: c.clientWidth, h: c.clientHeight }))"""
            )
            body_overflows = page.evaluate(
                "() => document.documentElement.scrollWidth > window.innerWidth"
            )
        finally:
            browser.close()

    assert not console_errors, f"{browser_name}: JS errors on the dashboard: {console_errors}"
    assert len(canvases) >= _MIN_VISIBLE_CANVASES, (
        f"{browser_name}: only {len(canvases)} visible canvases "
        f"(expected >= {_MIN_VISIBLE_CANVASES}): {canvases}"
    )

    collapsed = [c for c in canvases if c["w"] == 0 or c["h"] == 0]
    assert not collapsed, f"{browser_name}: canvases rendered with zero size: {collapsed}"
    assert not body_overflows, f"{browser_name}: page overflows horizontally"


# Fonts were fetched from fonts.googleapis.com at view time, so every dashboard
# and every exported report made a request to Google — in a product that says it
# runs locally and sends nothing. They are bundled now (frontend/src/themes/
# fonts.css, inlined into the stylesheet by every build).
_FACES = ('16px "DM Sans"', 'italic 16px "DM Sans"', '16px "Instrument Serif"')


def _launch(pw: object, browser_name: str) -> object:
    browser_type = getattr(pw, browser_name)
    try:
        return browser_type.launch()
    except Exception as exc:  # noqa: BLE001 — engine unavailable, not an app bug
        if _REQUIRE_ALL:
            pytest.fail(f"{browser_name} failed to launch: {exc}")
        pytest.skip(f"{browser_name} unavailable on this host: {exc}")


def _faces_loaded(page: object) -> dict[str, bool]:
    return page.evaluate(  # type: ignore[attr-defined, no-any-return]
        """async (faces) => {
            await document.fonts.ready;
            await Promise.all(faces.map((f) => document.fonts.load(f)));
            const loaded = [...document.fonts].filter((f) => f.status === 'loaded')
              .map((f) => f.family.replace(/["']/g, '') + '|' + f.style);
            return Object.fromEntries(faces.map((f) => {
              const style = f.startsWith('italic') ? 'italic' : 'normal';
              const family = f.split('"')[1];
              return [f, loaded.includes(family + '|' + style)];
            }));
        }""",
        list(_FACES),
    )


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_the_dashboard_asks_nothing_of_anyone_else(
    dashboard: tuple[str, str],
    browser_name: str,
) -> None:
    """Every request stays on this machine, and the bundled fonts are the ones drawn."""
    base_url, run_id = dashboard
    requested: list[str] = []
    with sync_playwright() as pw:
        browser = _launch(pw, browser_name)
        try:
            page = browser.new_page()  # type: ignore[attr-defined]
            page.on("request", lambda req: requested.append(req.url))
            page.goto(f"{base_url}/v/{run_id}", wait_until="networkidle")
            faces = _faces_loaded(page)
        finally:
            browser.close()  # type: ignore[attr-defined]
    foreign = [u for u in requested if not u.startswith((base_url, "data:", "blob:"))]
    assert not foreign, f"{browser_name}: requests left the machine: {foreign}"
    assert all(faces.values()), f"{browser_name}: bundled fonts not drawn: {faces}"


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_an_exported_report_works_offline_with_its_fonts(
    dashboard: tuple[str, str],
    tmp_path: Path,
    browser_name: str,
) -> None:
    """An exported HTML report opened with the network cut still draws its own fonts."""
    base_url, run_id = dashboard
    import urllib.request

    with urllib.request.urlopen(f"{base_url}/api/export/{run_id}/html") as resp:  # noqa: S310
        html = resp.read().decode("utf-8")
    report = tmp_path / "report.html"
    report.write_text(html, encoding="utf-8")

    blocked: list[str] = []
    with sync_playwright() as pw:
        browser = _launch(pw, browser_name)
        try:
            context = browser.new_context()  # type: ignore[attr-defined]

            def _offline(route: object) -> None:
                url = route.request.url  # type: ignore[attr-defined]
                if url.startswith(("file:", "data:", "blob:")):
                    route.continue_()  # type: ignore[attr-defined]
                else:
                    blocked.append(url)
                    route.abort()  # type: ignore[attr-defined]

            context.route("**/*", _offline)
            page = context.new_page()
            page.goto(report.as_uri())
            faces = _faces_loaded(page)
        finally:
            browser.close()  # type: ignore[attr-defined]
    assert not blocked, f"{browser_name}: the offline report reached for the network: {blocked}"
    assert all(faces.values()), f"{browser_name}: report fonts not drawn offline: {faces}"
