"""Visualize API — open a finished run in the browser."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from epochix.browser import open_in_browser

if TYPE_CHECKING:
    from epochix.config import Settings
    from epochix.models import Run


def _settings_for(db: str | None) -> Settings:
    """The configured settings, with *db* as the database when one is given.

    The app's startup opens its store on ``settings.db`` — whatever was set on
    the app before. ``visualize`` set a store on *db* and startup replaced it,
    and ``serve`` never read *db*; both served EPOCHIX_DB instead, so
    ``visualize(run, db=...)`` opened a dashboard on a run its own server could
    not find. The database has to travel in the settings.
    """
    from epochix.config import get_settings

    settings = get_settings()
    return settings.model_copy(update={"db": db}) if db else settings


def _warn_if_exposed(settings: Settings, host: str, port: int) -> None:
    """Both functions here take the address as an argument and bound it in
    silence; ``host="0.0.0.0"`` with no token put the write routes on the
    network. The CLI said so and the SDK did not."""
    from epochix.server.auth import PublicBindWarning, public_bind_warning

    message = public_bind_warning(settings, host, port)
    if message:
        # stacklevel 3: the caller of serve()/visualize(), not this helper.
        warnings.warn(message, PublicBindWarning, stacklevel=3)


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
        Bind address. Anything but loopback without ``EPOCHIX_AUTH_TOKEN``
        raises :class:`~epochix.server.auth.PublicBindWarning`.
    db:
        SQLite DB path that contains the run (defaults to the configured DB).
    blocking:
        If ``True`` (default), block until the user closes the server
        (Ctrl-C).  Set to ``False`` to start the server in a background
        thread and return immediately.

    Returns
    -------
    str
        The URL where the run is being served.
    """
    import uvicorn

    from epochix.server.app import create_app

    settings = _settings_for(db)
    _warn_if_exposed(settings, host, port)
    _app = create_app(settings=settings)

    url = f"http://{host}:{port}/v/{run.id}"
    open_in_browser(url)

    if blocking:
        uvicorn.run(_app, host=host, port=port, log_level="warning")
    else:
        import threading

        thread = threading.Thread(
            target=uvicorn.run,
            args=(_app,),
            kwargs={"host": host, "port": port, "log_level": "warning"},
            daemon=True,
        )
        thread.start()

    return url


def serve(
    port: int = 7860,
    host: str = "127.0.0.1",
    db: str | None = None,
    open_browser: bool = True,
) -> str:
    """Start the epochix server without a specific run.

    Serves the runs in *db* (defaults to the configured DB). Returns the base
    URL.  Blocks until the server is stopped. A *host* other
    than loopback without ``EPOCHIX_AUTH_TOKEN`` raises
    :class:`~epochix.server.auth.PublicBindWarning`.
    """
    import uvicorn

    from epochix.server.app import create_app

    settings = _settings_for(db)
    _warn_if_exposed(settings, host, port)
    _app = create_app(settings=settings)

    url = f"http://{host}:{port}"
    if open_browser:
        open_in_browser(url)

    uvicorn.run(_app, host=host, port=port, log_level="warning")
    return url
