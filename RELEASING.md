# Releasing Epochix

Everything code-side is automated. What remains before the first public
release is **account setup** — one-time, manual, roughly 60–90 minutes total.
Follow the steps in order; each later step depends on the earlier ones.

The end state: pushing a tag `vX.Y.Z` automatically publishes the wheel to
PyPI, the extension to the VS Code Marketplace + Open VSX, attaches the
`.vsix` + SBOM to a GitHub Release, and deploys the docs.

---

## Step 1 — GitHub organisation + repository (~10 min)

Everything in the repo (badges, `pyproject.toml` URLs, workflows) points at
`github.com/epochix/epochix`, so create it exactly like that:

1. Go to <https://github.com/organizations/plan> → **Create a free
   organization** → name: **`epochix`**.
   *If the name is taken, stop here and decide a new GitHub home — then ask
   Claude to update all repo URLs before pushing.*
2. In the new org: **New repository** → name **`epochix`**, public, **no**
   README/license/gitignore (the repo already has them).
3. On your machine:

   ```bash
   cd C:\Work\Personal\Mix\Gradus
   git remote add origin https://github.com/epochix/epochix.git
   git push -u origin main
   ```

4. Watch the **Actions** tab: the `CI` workflow must go green (lint,
   typecheck, tests on 3 OS × 4 Pythons, frontend tests, e2e).

### Repository settings (Settings tab)

| Setting | Where | Value |
|---|---|---|
| GitHub Pages | Pages → Build and deployment | Source: **GitHub Actions** (needed by `docs.yml`) |
| Private vulnerability reporting | Security → Code security | **Enable** (SECURITY.md points here) |
| Actions permissions | Actions → General | Allow GitHub Actions (default is fine) |

---

## Step 2 — PyPI trusted publisher (~10 min)

No API tokens needed — the release workflow authenticates via OIDC.

1. Create an account at <https://pypi.org> (enable 2FA — required).
2. Go to <https://pypi.org/manage/account/publishing/> →
   **Add a new pending publisher**:

   | Field | Value |
   |---|---|
   | PyPI project name | `epochix` |
   | Owner | `epochix` |
   | Repository name | `epochix` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   "Pending" means the project is created on first publish — this also
   **reserves the name** so nobody can squat it.
3. Nothing to configure in the repo: `release.yml` already declares
   `environment: pypi` and `id-token: write`.

---

## Step 3 — VS Code Marketplace publisher (~20 min)

The extension manifest says `"publisher": "epochix"`, so the publisher ID
must be exactly `epochix`.

1. **Azure DevOps account** (Microsoft's marketplace backend):
   sign in at <https://dev.azure.com> with any Microsoft account and create
   an organisation if prompted (any name — it's not user-visible).
2. **Personal Access Token**: in Azure DevOps, click the user-settings icon
   → **Personal access tokens** → *New Token*:
   - Name: `epochix-marketplace`
   - Organization: **All accessible organizations**  ← easy to miss, required
   - Expiration: up to 1 year (set a calendar reminder to rotate)
   - Scopes: **Custom defined** → *Marketplace* → **Manage**
   - Copy the token immediately (shown once).
3. **Create the publisher**: go to
   <https://marketplace.visualstudio.com/manage> → *Create publisher*:
   - ID: **`epochix`** (immutable, must match package.json)
   - Display name: `Epochix`
   *If the ID is taken, stop and ask Claude to change the `publisher` field
   + Marketplace URLs before tagging.*
4. **Store the secret**: GitHub → epochix/epochix → Settings → Secrets and
   variables → Actions → *New repository secret*:
   - Name: `VSCE_PAT`
   - Value: the token from step 2.

---

## Step 4 — Open VSX publisher (~15 min)

Open VSX serves VSCodium, Gitpod, Eclipse Theia etc. Optional but cheap.

1. Sign in at <https://open-vsx.org> with your GitHub account.
2. Sign the Eclipse publisher agreement when prompted (one click via
   your Eclipse account; create one if asked).
3. Claim the namespace: your first publish auto-creates it, but you can
   pre-claim `epochix` via <https://github.com/EclipseFdn/open-vsx.org/issues>
   (namespace ownership issue template) — recommended so the extension shows
   a "verified" publisher.
4. Access token: open-vsx.org → your avatar → *Settings* → *Access Tokens*
   → generate.
5. GitHub secret: name `OVSX_PAT`, value = that token.

> If you decide to skip Open VSX: delete the `publish-openvsx` job in
> `.github/workflows/vscode-release.yml` and remove it from
> `attach-release-asset`'s `needs:` list — otherwise the release shows a
> failed job.

---

## Step 5 — Docs domain (~5 min, or defer)

`docs.epochix.dev` is referenced in the README, pyproject and mkdocs.yml.
Two options:

- **Own `epochix.dev`**: buy the domain, then add a DNS `CNAME` record
  `docs` → `epochix.github.io`, and in the repo: Settings → Pages →
  Custom domain → `docs.epochix.dev` (+ enforce HTTPS).
- **Defer**: the docs also work at `https://epochix.github.io/epochix/`
  with zero setup (the `docs.yml` workflow deploys on every push to main).
  If you stay on this URL long-term, ask Claude to swap the
  `docs.epochix.dev` references.

---

## Step 6 — Dry-run release (~10 min)

Prove the whole pipeline without publishing anything:

```bash
git tag test/v0.3.0
git push origin test/v0.3.0
```

- `vscode-release.yml` runs fully but **skips** the Marketplace/Open VSX
  publish steps for `test/` tags; it uploads the packaged `.vsix` as a
  workflow artifact — download it and install manually in VS Code
  (Extensions panel → `…` → *Install from VSIX*) as a final smoke test.
- Delete the tag afterwards:
  `git push --delete origin test/v0.3.0 && git tag -d test/v0.3.0`

---

## Step 7 — The real release (~5 min + waiting)

```bash
git tag v0.3.0
git push origin v0.3.0
```

This triggers, in parallel:

| Workflow | What it publishes |
|---|---|
| `release.yml` | wheel → **PyPI** (OIDC), SBOM → GitHub Release |
| `vscode-release.yml` | `.vsix` → **VS Code Marketplace** + **Open VSX** + GitHub Release asset |

### Post-release verification checklist

- [ ] `pip install epochix` in a fresh venv → `epochix demo` shows a dashboard
- [ ] <https://pypi.org/project/epochix/> renders the README + logo correctly
- [ ] Marketplace listing live (search "Epochix" in VS Code) → install →
      `Ctrl+Alt+M` opens the dashboard
- [ ] GitHub Release has the `.vsix` and `sbom.cyclonedx.json` attached
- [ ] README badges resolve (PyPI version, CI, Marketplace)
- [ ] Docs live (Pages URL or custom domain)

---

## Future releases

1. Land changes on `main` with CHANGELOG entries under a new version heading.
2. Bump `version` in `pyproject.toml` **and** `frontend/package.json`
   (the extension version is stamped from the tag automatically).
3. Regenerate lockfiles if `package.json` changed:
   `npm --prefix frontend install --package-lock-only` (same for
   `epochix-vscode`) — CI's `npm ci` fails if they drift.
4. Tag `vX.Y.Z`, push the tag. Done.

## Known deferred items (not release blockers)

- **Google Fonts** are loaded from the CDN at dashboard runtime — a privacy
  and offline-purity tradeoff. Self-hosting the two families would add
  ~150 KB to the bundle; revisit if users ask for air-gapped mode.
- `websockets.legacy` deprecation warning via uvicorn — upstream; goes away
  with a future uvicorn bump.
- Store write throughput is advisory (~6–10k writes/sec depending on
  hardware); revisit batching if live runs ever log faster than that.
