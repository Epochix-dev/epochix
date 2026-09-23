"""The release bump must reach every file that records the version.

Four files carry it, and they drifted apart repeatedly when bumped by hand:

* `uv.lock` only refreshes when uv next resolves, so it sat a release behind
  after every release — three "chore: sync uv.lock" commits landed in one week.
* `epochix-vscode/package.json` drifted onto a 0.5.x line matching no tag.
* `epochix-vscode/package-lock.json` records the extension's version too, and
  sat at 0.5.76 through every release up to 0.7.10. The first version of this
  test said "three files" and checked three; it missed this one entirely.

The script fails loudly on a zero-match rather than reporting success and
leaving a version behind, which is the whole point of it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bump_version", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["bump_version"] = module
    spec.loader.exec_module(module)
    return module


bump = _load()


class TestVersionValidation:
    @pytest.mark.parametrize("bad", ["", "1.2", "abc", "1.2.3.4", "v", "0.7.x", "latest"])
    def test_a_non_version_is_refused(self, bad: str) -> None:
        with pytest.raises(SystemExit):
            bump.main([bad])

    @pytest.mark.parametrize("good", ["0.7.11", "1.0.0", "0.8.0-rc1", "v0.7.11"])
    def test_a_real_version_is_accepted(self, good: str, tmp_path: pathlib.Path) -> None:
        """Parsed and normalised — a leading `v` from a tag name is tolerated."""
        assert bump._SEMVER.match(good.lstrip("v")), good


class TestReplaceOnce:
    def test_it_rewrites_exactly_one_match(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "pyproject.toml"
        f.write_text('name = "x"\nversion = "0.1.0"\n', encoding="utf-8")
        bump._replace_once(f, r'(?m)^version = "[^"]+"', 'version = "9.9.9"')
        assert 'version = "9.9.9"' in f.read_text(encoding="utf-8")

    def test_it_fails_loudly_when_nothing_matches(self, tmp_path: pathlib.Path) -> None:
        """A silent no-op is the failure this script exists to prevent."""
        f = tmp_path / "pyproject.toml"
        f.write_text('name = "x"\n', encoding="utf-8")
        with pytest.raises(SystemExit, match="expected one match"):
            bump._replace_once(f, r'(?m)^version = "[^"]+"', 'version = "9.9.9"')


class TestLockfileWriter:
    def test_it_sets_both_fields_and_nothing_else(self, tmp_path: pathlib.Path) -> None:
        import json

        f = tmp_path / "package-lock.json"
        original = {
            "name": "x",
            "version": "0.5.76",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": {"name": "x", "version": "0.5.76", "devDependencies": {"a": "^1"}},
                "node_modules/a": {"version": "1.2.3"},
            },
        }
        f.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
        bump._set_lock_version(f, "9.9.9")
        after = json.loads(f.read_text(encoding="utf-8"))
        assert after["version"] == "9.9.9"
        assert after["packages"][""]["version"] == "9.9.9"
        # A dependency's own version is not the package's version.
        assert after["packages"]["node_modules/a"]["version"] == "1.2.3"

    def test_it_preserves_crlf(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "package-lock.json"
        body = '{\r\n  "version": "1.0.0",\r\n  "packages": {\r\n    "": {\r\n      "version": "1.0.0"\r\n    }\r\n  }\r\n}\r\n'
        f.write_bytes(body.encode("utf-8"))
        bump._set_lock_version(f, "2.0.0")
        raw = f.read_bytes().decode("utf-8")
        assert "\r\n" in raw and "\n" not in raw.replace("\r\n", ""), "line endings changed"


class TestTheRealPatternsStillMatch:
    """The regexes are only useful if they match the files as they are today."""

    def test_pyproject_has_exactly_one_top_level_version(self) -> None:
        import re

        text = (bump.ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert len(re.findall(r'(?m)^version = "[^"]+"', text)) == 1

    def test_the_extension_manifest_version_is_first(self) -> None:
        """The pattern takes the first `"version"`, so it must be the manifest's."""
        import json
        import re

        path = bump.ROOT / "epochix-vscode" / "package.json"
        text = path.read_text(encoding="utf-8")
        first = re.search(r'"version": "([^"]+)"', text)
        assert first is not None
        assert first.group(1) == json.loads(text)["version"], (
            "the first `version` in package.json is not the manifest's own"
        )

    def test_the_three_committed_files_agree(self) -> None:
        """A drift here is the bug the script was written to stop.

        Read out of git rather than off disk, and not for tidiness: `uv run`
        re-resolves and rewrites uv.lock *before* pytest starts, so a working
        tree assertion about the lock can never fail under CI's
        `uv run --extra dev pytest` — uv silently repairs the drift the test is
        looking for, and the test then passes for the wrong reason. What
        actually ships is what is committed.
        """
        import json
        import re
        import subprocess

        def committed(path: str) -> str | None:
            result = subprocess.run(
                ["git", "show", f"HEAD:{path}"],
                cwd=bump.ROOT,
                capture_output=True,
            )
            if result.returncode != 0:
                return None
            return result.stdout.decode("utf-8", "replace")

        pyproject = committed("pyproject.toml")
        if pyproject is None:
            pytest.skip("not a git checkout")

        match = re.search(r'(?m)^version = "([^"]+)"', pyproject)
        assert match, "no version in the committed pyproject.toml"
        version = match.group(1)

        manifest_text = committed("epochix-vscode/package.json")
        assert manifest_text is not None
        manifest = json.loads(manifest_text)["version"]
        assert manifest == version, (
            f"committed extension manifest is {manifest}, pyproject is {version} "
            f"— run `make bump VERSION=<v>` instead of editing by hand"
        )

        lock = committed("uv.lock")
        assert lock is not None
        pattern = 'name = "epochix"' + r"\r?\n" + 'version = "' + re.escape(version) + '"'
        assert re.search(pattern, lock), (
            f"committed uv.lock does not record {version} — run "
            f"`make bump VERSION=<v>`, which runs `uv lock` for you"
        )

        npm_lock_text = committed("epochix-vscode/package-lock.json")
        assert npm_lock_text is not None
        npm_lock = json.loads(npm_lock_text)
        recorded = {npm_lock["version"], npm_lock["packages"][""]["version"]}
        assert recorded == {version}, (
            f"committed epochix-vscode/package-lock.json records {sorted(recorded)}, "
            f"pyproject is {version} — run `make bump VERSION=<v>`"
        )
