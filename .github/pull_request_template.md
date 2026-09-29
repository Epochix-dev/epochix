## What and why

<!-- What does this change, and what was wrong before? A log excerpt or a
     screenshot of the wrong output helps more than a description of it. -->

## Checklist

- [ ] A test that runs the new path end to end (see [AGENTS.md](../AGENTS.md#tests-must-execute-the-path))
- [ ] If a parser changed: the same fix in both `src/epochix/parsers/` and `epochix-vscode/src/parsers/`
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] The gate, run separately (not chained with `&&`):
  - `uv run --extra dev ruff check src tests`
  - `uv run --extra dev ruff format --check src tests`
  - `uv run --extra dev mypy --strict src/epochix`
  - `uv run --extra dev pytest tests/unit tests/integration`
- [ ] Nothing shown to users is invented: no placeholder numbers, no sample
      output passed off as real
