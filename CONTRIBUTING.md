# Contributing to Epochix

Thanks for taking the time to contribute. Epochix lives by clear narratives,
honest metrics, and reproducible builds — your patches should match.

## Quick start

```bash
git clone https://github.com/epochix/epochix
cd epochix
pip install -e ".[dev]"
pre-commit install
pytest tests/unit tests/integration
```

For the frontend or the VS Code extension:

```bash
cd frontend           && npm ci && npm test
cd ../epochix-vscode  && npm ci && npx tsc --noEmit
```

## Branching + commits

- Branch off `main` (`feat/<slug>`, `fix/<slug>`, `docs/<slug>`).
- Conventional-Commit style for the subject line, lowercase scope:
  `fix(viz): keep zone labels visible on narrow canvases`.
- Reference the issue in the body if there is one.

## Coding standards

| Layer        | Tool                  | Run                                   |
|--------------|-----------------------|---------------------------------------|
| Python lint  | `ruff`                | `ruff check src tests`                |
| Python type  | `mypy --strict`       | `mypy --strict src/epochix`           |
| Python tests | `pytest`              | `pytest tests/unit tests/integration` |
| Frontend     | `vitest`              | `cd frontend && npm test`             |
| VS Code      | `tsc --noEmit`        | `cd epochix-vscode && npx tsc --noEmit` |

CI runs all of the above on Linux / macOS / Windows × Python 3.10–3.13.
A patch is mergeable when every check passes locally and in CI.

## Pull-request checklist

- [ ] Tests for the new behaviour (and a regression test if you fixed a bug)
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Docs updated if you changed CLI flags, env vars, or the SDK
- [ ] No new warnings from `ruff` / `mypy --strict`
- [ ] No vendored binaries (`*.png`, `*.whl`, `*.vsix`) added without a reason

## Reporting issues

Please open an issue at <https://github.com/epochix/epochix/issues>. For
security-relevant problems, follow [SECURITY.md](SECURITY.md) instead — don't
open a public issue.

## License

By contributing you agree your work is licensed under the Apache License 2.0
(see [LICENSE](LICENSE)).
