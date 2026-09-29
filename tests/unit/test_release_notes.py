"""Every release has notes, taken from its CHANGELOG section.

All 136 GitHub releases were published with an empty body. The release
workflow now publishes the version's CHANGELOG section (scripts/
release_notes.py); these check the extractor on the real file, and that the
version being built right now has a section — without one the release step
fails, which is the point, but it should fail here first.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_notes", REPO / "scripts" / "release_notes.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_current_version_has_notes() -> None:
    # A regex, not tomllib: CI still runs Python 3.10.
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert m, "no version in pyproject.toml"
    version = m.group(1)
    notes = _script().section(version)
    assert notes, f"CHANGELOG.md has no section for {version}; the release would have no notes"
    assert notes.startswith("### ")


def test_a_section_stops_at_the_next_version() -> None:
    text = (
        "# Changelog\n\n## [Unreleased]\n\n## [1.1.0] — 2026-01-02\n\n### Fixed\n\n- b\n\n"
        "---\n\n## [1.0.0] — 2026-01-01\n\n### Added\n\n- a\n\n[1.0.0]: https://example.com\n"
    )
    script = _script()
    assert script.section("1.1.0", text) == "### Fixed\n\n- b"
    assert script.section("1.0.0", text) == "### Added\n\n- a"
    assert script.section("2.0.0", text) is None


def test_the_workflow_publishes_them() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "scripts/release_notes.py" in workflow
    assert "body_path: release-notes.md" in workflow
