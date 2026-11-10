"""Where the run a caller is holding is stored.

``parse()`` keeps a run in memory unless it is given ``db=``, and ``export()``,
``compare()`` and ``visualize()`` looked for it in the configured database. So
``export(parse("train.log"))`` raised "Run not found" in every format, and
``compare()`` returned its verdict without the narrative, for the life of the
SDK: no test called any of them (found by the first coverage run, 2026-11-10).

``parse()`` now notes the store it wrote the run into, and the others ask here.
The note lasts as long as the ``Run`` object ``parse()`` returned: an in-memory
database is a few hundred kilobytes, and a script that parses a thousand logs
in a loop must not be left holding a thousand of them.
"""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from epochix.models import Run
    from epochix.store.sqlite_store import RunStore

# run id -> the store parse() wrote it into, while that Run object is alive.
_parsed_into: dict[str, RunStore] = {}


def remember(run: Run, store: RunStore) -> None:
    """Note that *run* was written into *store*, until *run* is collected."""
    _parsed_into[run.id] = store
    weakref.finalize(run, _forget, run.id, store)


def _forget(run_id: str, store: RunStore) -> None:
    # Only the note this Run made: a later parse() given the same run_id has
    # written its own, and must keep it.
    if _parsed_into.get(run_id) is store:
        del _parsed_into[run_id]


def store_for(run: Run, db: str | None) -> RunStore:
    """The store to read *run* from.

    *db* when the caller names one; otherwise the store ``parse()`` wrote this
    run into; otherwise the configured database, which is where the CLI, the
    server and ``LiveReporter`` keep theirs.
    """
    from epochix.store.sqlite_store import RunStore

    if db is not None:
        return RunStore(db_path=db)
    known = _parsed_into.get(run.id)
    if known is not None:
        return known
    from epochix.config import get_settings

    return RunStore(db_path=get_settings().db)


def store_holding(run: Run, db: str | None) -> RunStore:
    """:func:`store_for`, or a ``ValueError`` saying where the run was not."""
    store = store_for(run, db)
    if store.get_run(run.id) is not None:
        return store
    if db is None:
        from epochix.config import get_settings

        where = f"the configured database ({get_settings().db})"
    else:
        where = db
    raise ValueError(
        f"Run not found: {run.id!r} is not in {where}. A run returned by parse() "
        "is found without db= for as long as that Run object is kept; for any "
        "other run, pass the db= it was stored in."
    )
