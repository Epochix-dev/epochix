"""pytest-benchmark 5.3.0 reads `node._nodeid`, which pytest 9.2 removed.

Its main branch already reads `nodeid`, unreleased. Until then the node gets the
attribute before the `benchmark` fixture is built; on a version that has it, or a
pytest-benchmark that no longer asks, this does nothing that matters.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _node_keeps_its_private_id(request: pytest.FixtureRequest) -> None:
    if not hasattr(request.node, "_nodeid"):
        request.node._nodeid = request.node.nodeid
