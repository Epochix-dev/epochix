"""Opening the dashboard in a browser — the one place that does it.

`EPOCHIX_OPEN_BROWSER` was documented ("Open a browser when a run starts") and
read by nothing: every command and the SDK called `webbrowser.open` directly,
so setting it to false on a server or in CI changed nothing. Everything that
opens a browser now comes through here.
"""

from __future__ import annotations

import webbrowser

from epochix.config import get_settings


def open_in_browser(url: str) -> bool:
    """Open *url* unless `EPOCHIX_OPEN_BROWSER` is off; True when it was opened."""
    if not get_settings().open_browser:
        return False
    webbrowser.open(url)
    return True
