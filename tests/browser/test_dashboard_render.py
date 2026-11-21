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

import contextlib
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


@pytest.fixture(scope="session")
def empty_dashboard(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The dashboard served over a database with no run in it."""
    if not _FRONTEND_INDEX.is_file():
        msg = "frontend bundle not built — see the `dashboard` fixture"
        if _REQUIRE_ALL:
            pytest.fail(msg)
        pytest.skip(msg)
    db_path = str(tmp_path_factory.mktemp("browser-empty") / "runs.db")
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
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_the_report_button_with_nothing_loaded_explains_first(
    empty_dashboard: str,
    browser_name: str,
) -> None:
    """Both outside reports in the first month were blank forms filed from an
    empty panel. With nothing loaded, the button says what Epochix reads, and
    a report is still one click further — asking what the person was doing."""
    with sync_playwright() as pw:
        browser = _launch(pw, browser_name)
        try:
            page = browser.new_page()  # type: ignore[attr-defined]
            # Record where a report would go instead of leaving the machine.
            page.add_init_script(
                "window.__opened = []; window.open = (url) => { window.__opened.push(url); return null; };"
            )
            page.goto(f"{empty_dashboard}/", wait_until="networkidle")
            page.click("#report-btn")
            prompt = page.wait_for_selector(".report-prompt", timeout=5000)
            text = prompt.inner_text()
            assert "not your source code" in text, text
            assert "epochix demo" in text, text
            assert page.evaluate("window.__opened.length") == 0, "a blank form opened first"

            page.click(".report-anyway")
            page.wait_for_function("window.__opened.length === 1", timeout=5000)
            url = page.evaluate("window.__opened[0]")
            assert url.startswith("https://github.com/Epochix-dev/epochix/issues/new"), url
            assert "What%20were%20you%20trying%20to%20do" in url, url
            assert page.query_selector(".report-prompt") is None, "the prompt stayed open"
        finally:
            browser.close()  # type: ignore[attr-defined]


def _timeline_text(page: object) -> str:
    return page.evaluate(  # type: ignore[attr-defined, no-any-return]
        "() => [...document.querySelectorAll('.timeline-card')].map(c => c.innerText).join(' | ')"
    )


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_a_finished_run_and_its_report_show_their_milestones(
    dashboard: tuple[str, str],
    tmp_path: Path,
    browser_name: str,
) -> None:
    """The timeline of a run opened after it finished, and of its exported
    report, shows the run's milestones. Both showed none: milestones were
    stored and never read back, and reached a page only while it watched."""
    base_url, run_id = dashboard
    import json
    import urllib.request

    with urllib.request.urlopen(f"{base_url}/api/snapshot/{run_id}") as resp:  # noqa: S310
        stored = json.loads(resp.read().decode("utf-8"))["milestones"]
    expected = [m["message"] for m in stored if m["kind"] != "training_complete"]
    assert len(expected) >= 3, stored

    with urllib.request.urlopen(f"{base_url}/api/export/{run_id}/html") as resp:  # noqa: S310
        report = tmp_path / "report.html"
        report.write_text(resp.read().decode("utf-8"), encoding="utf-8")

    with sync_playwright() as pw:
        browser = _launch(pw, browser_name)
        try:
            for where in (f"{base_url}/v/{run_id}", report.as_uri()):
                page = browser.new_page()  # type: ignore[attr-defined]
                page.goto(where)
                page.wait_for_function(
                    "(n) => document.querySelectorAll('.timeline-card').length >= n",
                    arg=len(expected),
                    timeout=15_000,
                )
                shown = _timeline_text(page)
                missing = [m for m in expected if m not in shown]
                assert not missing, f"{browser_name} {where}: not on the timeline: {missing}"
                assert shown.lower().count("training complete") == 1, shown
                page.close()
        finally:
            browser.close()  # type: ignore[attr-defined]


class _RefusingProxy:
    """A reverse proxy that refuses WebSocket upgrades and relays the rest.

    The setup the SSE feed exists for: a strict corporate proxy answers the
    upgrade with an error, and serves pages and streams as usual. The dashboard
    chose SSE on `'WebSocket' in window`, which every browser satisfies, so
    behind one it stayed on a WebSocket that never opened and was never live.
    """

    def __init__(self, upstream_port: int) -> None:
        self.upstream_port = upstream_port
        self.refused = 0
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(32)
        self.port: int = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self) -> None:
        self._listener.close()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client: socket.socket) -> None:
        head = b""
        try:
            while b"\r\n\r\n" not in head:
                chunk = client.recv(65536)
                if not chunk:
                    client.close()
                    return
                head += chunk
            if b"\r\nupgrade: websocket" in head.lower():
                self.refused += 1
                client.sendall(
                    b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
                client.close()
                return
            upstream = socket.create_connection(("127.0.0.1", self.upstream_port))
        except OSError:
            client.close()
            return
        upstream.sendall(head)

        def pump(src: socket.socket, dst: socket.socket) -> None:
            try:
                while chunk := src.recv(65536):
                    dst.sendall(chunk)
            except OSError:
                pass
            finally:
                for s in (src, dst):
                    with contextlib.suppress(OSError):
                        s.shutdown(socket.SHUT_RDWR)

        threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
        pump(client, upstream)


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_behind_a_proxy_that_refuses_websockets_the_run_is_live_over_sse(
    tmp_path: Path,
    browser_name: str,
) -> None:
    """A live run, watched through a proxy that blocks the WebSocket upgrade,
    is told as it runs: the page hands over to /sse/live and shows each new
    frame, and ends with the run."""
    if not _FRONTEND_INDEX.is_file():
        msg = "frontend bundle not built — see the `dashboard` fixture"
        if _REQUIRE_ALL:
            pytest.fail(msg)
        pytest.skip(msg)
    from tests.live_cli import LiveCli, epoch_line

    cli = LiveCli(tmp_path)
    proxy = _RefusingProxy(cli.port)
    page_errors: list[str] = []
    requested: list[str] = []
    try:
        cli.write(*(epoch_line(e, of=8) for e in range(1, 4)))
        run_id = cli.run_id()
        cli.wait_for_frames(run_id, 1)

        with sync_playwright() as pw:
            browser = _launch(pw, browser_name)
            try:
                page = browser.new_page()  # type: ignore[attr-defined]
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                page.on("request", lambda req: requested.append(req.url))
                page.goto(f"http://127.0.0.1:{proxy.port}/v/{run_id}")
                page.wait_for_function(
                    "document.getElementById('connection-dot').classList.contains('live')",
                    timeout=20_000,
                )
                assert proxy.refused >= 1, "the page never tried the WebSocket"
                assert any("/sse/live/" in u for u in requested), requested

                # What the run says next reaches the open page.
                before = len(cli.frames(run_id))
                cli.write(epoch_line(4, of=8), epoch_line(5, of=8))
                cli.wait_for_frames(run_id, before + 2)
                latest = str(cli.frames(run_id)[-1]["narrative"])
                page.wait_for_function(
                    "(text) => document.body.innerText.includes(text)",
                    arg=latest,
                    timeout=20_000,
                )

                cli.write(*(epoch_line(e, of=8) for e in range(6, 9)))
                assert cli.finish() == 0
                page.wait_for_function(
                    "!document.getElementById('connection-dot').classList.contains('live')",
                    timeout=20_000,
                )
            finally:
                browser.close()  # type: ignore[attr-defined]
    finally:
        proxy.close()
        cli.stop()
    assert not page_errors, f"{browser_name}: page errors: {page_errors}"


# ── a server started with EPOCHIX_AUTH_TOKEN ──────────────────────────────────
#
# The read routes want `Authorization: Bearer`, the live feeds `?token=`. The
# dashboard sent neither, so with a token set it could not load a run at all —
# while the docs offered the token as the way to run the dashboard remotely. A
# reader now opens a page once with `?token=`; the page keeps it for the tab and
# sends it on every request (frontend/src/auth.js).

_TOKEN = "browser-test-token-7f3a91"


def _links(page: object) -> list[str]:
    return page.eval_on_selector_all(  # type: ignore[attr-defined, no-any-return]
        "a[href]", "els => els.map((a) => a.href)"
    )


def _dot_is_live(page: object, live: bool = True) -> None:
    check = "document.getElementById('connection-dot').classList.contains('live')"
    page.wait_for_function(check if live else f"!{check}", timeout=20_000)  # type: ignore[attr-defined]


@pytest.mark.parametrize("via", ["websocket", "sse"])
@pytest.mark.parametrize("browser_name", BROWSERS)
def test_with_a_token_the_dashboard_loads_a_run_and_goes_live(
    tmp_path: Path,
    browser_name: str,
    via: str,
) -> None:
    """A live run on a server that wants a token: opened without it the page
    says how to give it; opened once with `?token=`, it loads the run, goes live
    (over the WebSocket, or over SSE behind a proxy that refuses the upgrade),
    keeps the token for the next page in the tab, and puts it in no link."""
    if not _FRONTEND_INDEX.is_file():
        msg = "frontend bundle not built — see the `dashboard` fixture"
        if _REQUIRE_ALL:
            pytest.fail(msg)
        pytest.skip(msg)
    from tests.live_cli import LiveCli, epoch_line

    cli = LiveCli(tmp_path, token=_TOKEN)
    proxy = _RefusingProxy(cli.port) if via == "sse" else None
    base = f"http://127.0.0.1:{proxy.port}" if proxy else cli.base_url
    page_errors: list[str] = []
    try:
        cli.write(*(epoch_line(e, of=8) for e in range(1, 4)))
        run_id = cli.run_id()
        cli.wait_for_frames(run_id, 1)

        with sync_playwright() as pw:
            browser = _launch(pw, browser_name)
            try:
                # Without the token: refused, and told what to do about it.
                page = browser.new_page()  # type: ignore[attr-defined]
                page.goto(f"{base}/v/{run_id}")
                page.wait_for_function(
                    "document.getElementById('toasts').innerText.includes('?token=')",
                    timeout=20_000,
                )
                page.close()

                page = browser.new_page()  # type: ignore[attr-defined]
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                page.goto(f"{base}/v/{run_id}?token={_TOKEN}")
                _dot_is_live(page)
                if proxy:
                    assert proxy.refused >= 1, "the page never tried the WebSocket"
                # Taken out of the address bar at once, and in no link.
                assert _TOKEN not in page.url, page.url
                assert not [u for u in _links(page) if _TOKEN in u]

                # The run as loaded, and what it says next, reach the page.
                shown = str(cli.frames(run_id)[-1]["narrative"])
                page.wait_for_function(
                    "(text) => document.body.innerText.includes(text)", arg=shown, timeout=20_000
                )
                before = len(cli.frames(run_id))
                cli.write(epoch_line(4, of=8), epoch_line(5, of=8))
                cli.wait_for_frames(run_id, before + 2)
                latest = str(cli.frames(run_id)[-1]["narrative"])
                page.wait_for_function(
                    "(text) => document.body.innerText.includes(text)", arg=latest, timeout=20_000
                )

                # The next page in this tab, reached by a link carrying no
                # token: the run list loads, and so does the run from it.
                page.click('.nav-item[href="/"]')
                page.wait_for_selector(f'a.run-open[href="/v/{run_id}"]', timeout=20_000)
                assert not [u for u in _links(page) if _TOKEN in u]
                page.click(f'a.run-open[href="/v/{run_id}"]')
                _dot_is_live(page)

                cli.write(*(epoch_line(e, of=8) for e in range(6, 9)))
                assert cli.finish() == 0
                _dot_is_live(page, live=False)
            finally:
                browser.close()  # type: ignore[attr-defined]
    finally:
        if proxy:
            proxy.close()
        cli.stop()
    assert not page_errors, f"{browser_name}: page errors: {page_errors}"


@pytest.fixture
def token_server(tmp_path: Path) -> Iterator[tuple[str, list[str]]]:
    """`epochix serve` with EPOCHIX_AUTH_TOKEN set, over two parsed runs."""
    if not _FRONTEND_INDEX.is_file():
        msg = "frontend bundle not built — see the `dashboard` fixture"
        if _REQUIRE_ALL:
            pytest.fail(msg)
        pytest.skip(msg)
    import subprocess
    import sys
    import urllib.request

    db = str(tmp_path / "runs.db")
    logs = Path(__file__).parents[1] / "fixtures" / "logs"
    ids = [
        parse(logs / name, db=db, run_name=f"browser/{name}").id
        for name in ("keras_50ep.log", "huggingface_5ep.log")
    ]
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 — this package's own CLI
        [sys.executable, "-m", "epochix.cli", "serve", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=tmp_path,
        env={**os.environ, "EPOCHIX_DB": db, "EPOCHIX_AUTH_TOKEN": _TOKEN},
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=2):  # noqa: S310
                    break
            except OSError:
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("epochix serve did not start") from None
                time.sleep(0.1)
        yield base, ids
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_with_a_token_an_exported_report_does_not_carry_it(
    token_server: tuple[str, list[str]],
    browser_name: str,
) -> None:
    """Every export a reader can save from a token-protected server — the run's
    HTML, Markdown and JSON, and the comparison's Markdown — downloads, and the
    token is written into none of them."""
    base, (run_id, other_id) = token_server
    saved: dict[str, str] = {}
    with sync_playwright() as pw:
        browser = _launch(pw, browser_name)
        try:
            context = browser.new_context(accept_downloads=True)  # type: ignore[attr-defined]
            page = context.new_page()
            page.goto(f"{base}/v/{run_id}?token={_TOKEN}", wait_until="networkidle")
            for fmt in ("html", "md", "json"):
                page.click("#export-btn")
                with page.expect_download(timeout=20_000) as dl:
                    page.click(f'.export-opt[data-fmt="{fmt}"]')
                saved[fmt] = Path(dl.value.path()).read_text(encoding="utf-8")

            # The comparison, in the same tab, opened with no token in its URL.
            page.goto(f"{base}/compare?runs={run_id},{other_id}", wait_until="networkidle")
            with page.expect_download(timeout=20_000) as dl:
                page.click("#cmp-md")
            saved["compare.md"] = Path(dl.value.path()).read_text(encoding="utf-8")
        finally:
            browser.close()  # type: ignore[attr-defined]

    assert set(saved) == {"html", "md", "json", "compare.md"}
    assert run_id in saved["html"] and 'id="run-data"' in saved["html"]
    assert run_id in saved["json"]
    for name in ("md", "compare.md"):
        assert len(saved[name].strip()) > 100, f"{name} is empty: {saved[name]!r}"
    carrying = [name for name, text in saved.items() if _TOKEN in text]
    assert not carrying, f"{browser_name}: the token was written into {carrying}"
