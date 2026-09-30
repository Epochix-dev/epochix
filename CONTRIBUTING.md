# Contributing to Epochix

Thanks for taking the time to contribute. Epochix lives by clear narratives,
honest metrics, and reproducible builds — your patches should match. Everyone
taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Quick start

```bash
git clone https://github.com/epochix-dev/epochix
cd epochix
uv run --extra dev pytest tests/unit tests/integration
```

Use `uv run`, exactly as CI does. A bare `pytest` on a machine that also has
epochix installed resolves the package from site-packages, and your edits
appear to do nothing. [AGENTS.md](AGENTS.md) collects the other traps this
repository has taught — read it before a non-trivial change.

For the frontend or the VS Code extension, one command per line — Windows
PowerShell 5.1 rejects `&&`:

```bash
cd frontend
npm ci
npm test
cd ../epochix-vscode
npm ci
npm test   # launches a real VS Code host
```

## Branching + commits

- Branch off `main` (`feat/<slug>`, `fix/<slug>`, `docs/<slug>`).
- Conventional-Commit style for the subject line, lowercase scope:
  `fix(viz): keep zone labels visible on narrow canvases`.
- Reference the issue in the body if there is one.

## Coding standards

| Layer         | Run                                                      |
|---------------|----------------------------------------------------------|
| Python lint   | `uv run --extra dev ruff check src tests`                |
| Python format | `uv run --extra dev ruff format --check src tests`       |
| Python type   | `uv run --extra dev mypy --strict src/epochix`           |
| Python tests  | `uv run --extra dev pytest tests/unit tests/integration` |
| Frontend      | `npm test` in `frontend/`                                |
| VS Code       | `npm test` in `epochix-vscode/`                          |

Run them separately. Chained with `&&`, an early failure silently skips the
rest — and Windows PowerShell 5.1 does not accept `&&` at all.

CI runs all of the above on Linux / macOS / Windows × Python 3.10–3.13.
A patch is mergeable when every check passes locally and in CI.

## Pull-request checklist

- [ ] Tests for the new behaviour (and a regression test if you fixed a bug)
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Docs updated if you changed CLI flags, env vars, or the SDK
- [ ] No new warnings from `ruff` / `mypy --strict`
- [ ] No vendored binaries (`*.png`, `*.whl`, `*.vsix`) added without a reason

## Reporting issues

Please open an issue at <https://github.com/epochix-dev/epochix/issues>. For
security-relevant problems, follow [SECURITY.md](SECURITY.md) instead — don't
open a public issue.

## License

By contributing you agree your work is licensed under the Apache License 2.0
(see [LICENSE](LICENSE)).
