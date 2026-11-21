"""Tests that need what the wheel vendors, and the job that has it.

The dashboard bundle (`epochix/_frontend/dist`) and the brand mark
(`epochix/_brand/mark.png`) are put into the package when the wheel is
built; a source checkout has neither. Tests that need them used to skip, and
skipped in every CI job: the HTML export's check that run data cannot break
out of its `<script>` block ran nowhere, and two HTML route tests accepted
200 or 501 and so passed on the 501.

They are marked `packaged_assets`. Anywhere else they still skip, or accept
the 501. CI's `packaged-assets` job builds the wheel exactly as the release
does, puts its assets into `src/epochix`, sets
`EPOCHIX_REQUIRE_PACKAGED_ASSETS=1` and runs `-m packaged_assets`: there a
missing asset is a failure, not a skip.
"""

from __future__ import annotations

import os
from typing import NoReturn

import pytest

ENV = "EPOCHIX_REQUIRE_PACKAGED_ASSETS"

#: True in the job that vendored the wheel's assets.
REQUIRED = os.environ.get(ENV) == "1"


def unavailable(what: str) -> NoReturn:
    """Skip for want of *what*, or fail if this job promised to have it."""
    if REQUIRED:
        pytest.fail(f"{what} is missing, and {ENV}=1 says this job vendored it from the wheel")
    pytest.skip(f"{what} is vendored into the wheel; absent in a source checkout")
