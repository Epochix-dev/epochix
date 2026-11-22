"""Every plugin group the docs name is one the code loads, and no other.

`docs/plugins.md`, `ARCHITECTURE.md` and the README listed four entry-point
groups for the life of the project. Two of them, `epochix.metaphor_packs` and
`epochix.tasks`, were read by nothing: their loaders had no caller, and an
installed plugin changed no card and no grade. They were removed on
2026-11-18. This ties the documentation to the `entry_points(group=...)`
calls in the source, so a group cannot again be documented without being
loaded, or loaded without being documented.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "epochix"

_LOADED = re.compile(r"""entry_points\(\s*group\s*=\s*["'](epochix\.[a-z_]{1,64})["']""")
_DOC_ROW = re.compile(r"^\|\s*`(epochix\.[a-z_]{1,64})`\s*\|", re.MULTILINE)


def _loaded_groups() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        found.update(_LOADED.findall(path.read_text(encoding="utf-8")))
    return found


def _table_groups(path: Path) -> set[str]:
    return set(_DOC_ROW.findall(path.read_text(encoding="utf-8")))


def test_the_source_loads_the_two_groups() -> None:
    # Guard: if the pattern stopped matching, every comparison below would
    # compare two empty sets and pass.
    assert _loaded_groups() == {"epochix.parsers", "epochix.exporters"}


def test_the_plugin_docs_list_exactly_the_loaded_groups() -> None:
    assert _table_groups(ROOT / "docs" / "plugins.md") == _loaded_groups()


def test_the_architecture_doc_lists_exactly_the_loaded_groups() -> None:
    assert _table_groups(ROOT / "ARCHITECTURE.md") == _loaded_groups()


def test_the_removed_groups_have_no_code_left() -> None:
    for name in ("metaphor_loader.py", "task_registry.py"):
        assert not (SRC / "plugins" / name).exists(), name
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for symbol in ("TaskDefinition", "load_yaml_pack", "get_metaphor_cards"):
            assert symbol not in text, f"{symbol} in {path.relative_to(ROOT)}"
