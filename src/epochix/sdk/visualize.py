"""Visualize API — open a finished run in the browser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from epochix.browser import open_in_browser

if TYPE_CHECKING:
    from epochix.models import Run


def visualize(
    run: Run,
    *,
    port: int = 7860,
    host: str = "127.0.0.1",
    db: str | None = None,
    blocking: bool = True,
) -> str:
    """Serve a finished run and open it in the browser.

    Parameters
    ----------
    run:
        A :class:`~epochix.models.Run` previously returned by
        :func:`~epochix.sdk.parse.parse`.
    port:
        Port for the embedded server.
    host:
        Bind address.
    db:
        SQLite DB path that contains the run.  Not needed for a run returned
        by :func:`~epochix.sdk.parse.parse`, which is served from where it was
        parsed into; for any other run it defaults to the configured DB.
    blocking:
        If ``True`` (default), block until the user closes the server
        (Ctrl-C).  Set to ``False`` to start the server in a background
        thread and return immediately.

    Returns
    -------
    str
        The URL where the run is being served.

    Raises
    ------
    ValueError
        If the run is not in the database it was looked for in.  No server is
        started and no page is opened.
    """
    import uvicorn

    from epochix.config import get_settings
    from epochix.sdk._stores import store_holding
    from epochix.server.app import create_app
    from epochix.server.hub import Hub

    # Before anything is opened: a page for a run the server does not have is
    # an empty dashboard with no explanation.
    store = store_holding(run, db)

    _app = create_app(settings=get_settings())
    _app.state.store = store
    _app.state.hub = Hub()
    _app.state.engine_map = {}

    url = f"http://{host}:{port}/v/{run.id}"
    open_in_browser(url)

    # lifespan="off": the app's own startup opens the configured database and
    # puts it where the store above was just put. Left on, `db=` was ignored
    # and a run parsed into memory was never the one served.
    server = uvicorn.Server(
        uvicorn.Config(_app, host=host, port=port, log_level="warning", lifespan="off")
    )
    if blocking:
        server.run()
    else:
        import threading

        threading.Thread(target=server.run, daemon=True, name="epochix-visualize").start()

    return url


def serve(
    port: int = 7860,
    host: str = "127.0.0.1",
    db: str | None = None,
    open_browser: bool = True,
) -> str:
    """Start the epochix server without a specific run.

    *db* is the SQLite DB to serve; the configured DB when ``None``.

    Returns the base URL.  Blocks until the server is stopped.
    """
    import uvicorn

    from epochix.config import get_settings
    from epochix.server.app import create_app

    settings = get_settings()
    if db is not None:
        # `db` was accepted and read by nothing: the configured DB was served
        # whatever was passed.
        settings = settings.model_copy(update={"db": db})
    _app = create_app(settings=settings)

    url = f"http://{host}:{port}"
    if open_browser:
        open_in_browser(url)

    uvicorn.Server(uvicorn.Config(_app, host=host, port=port, log_level="warning")).run()
    return url
