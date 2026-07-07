# Releasing Epochix — the complete walkthrough

Everything code-side is automated. What remains before the first public
release is **one-time account setup**, done by a human (~60–90 minutes).
Follow the steps in order; each later step depends on earlier ones.

**End state:** pushing a tag `vX.Y.Z` automatically publishes the wheel to
PyPI, the extension to the VS Code Marketplace + Open VSX, attaches the
`.vsix` and SBOM to a GitHub Release, and deploys the documentation.

> UI labels below are accurate as of early 2026. Websites move buttons
> around — if a label doesn't match, look for the closest equivalent
> rather than assuming you're on the wrong page.

---

## Before you start — what you need on hand

- [ ] Your GitHub account (`kv4u`), logged in
- [ ] An email address you check (verification mails arrive at every step)
- [ ] An authenticator app on your phone (Microsoft Authenticator, Authy,
      1Password, …) — PyPI **requires** 2FA
- [ ] A Microsoft account (any @outlook/@hotmail/@live login, or create one
      during Step 3) — needed for the VS Code Marketplace
- [ ] A password manager open, to store the two tokens you'll generate
- [ ] Money only if you buy the `epochix.dev` domain (Step 5, optional)

---

## Step 1 — GitHub organisation + repository (~10 min)

Everything in the repo (badges, `pyproject.toml` URLs, workflow
environments) points at `github.com/epochix/epochix`, so it must be created
with exactly those names.

### 1a. Create the organisation

1. Log in to GitHub → click the **+** icon (top-right) → **New organization**.
2. Choose the **Free** plan.
3. Fill the form:
   - **Organization name:** `epochix`
     — GitHub validates instantly. **If it says the name is taken, STOP.**
     Don't improvise a different name: the repo, badges and PyPI publisher
     config all assume `epochix`. Come back to Claude first, decide a new
     home together, and let Claude rewrite every URL before anything is
     pushed.
   - **Contact email:** yours.
   - **Belongs to:** *My personal account*.
4. Skip the "invite members" screen (*Skip this step*).

### 1b. Create the repository

1. Inside the new org (github.com/epochix) → **Repositories** tab →
   **New repository**.
2. Fill the form:
   - **Owner:** `epochix` (pick from the dropdown — not your personal account)
   - **Repository name:** `epochix`
   - Visibility: **Public**
   - **Do NOT tick** "Add a README", "Add .gitignore" or "Choose a license"
     — the project already has all three; initializing would create a
     conflicting first commit.
3. Click **Create repository**. You land on the empty-repo page — ignore
   its suggested commands; ours differ slightly.

### 1c. Push the code

In a terminal on this machine:

```powershell
cd C:\Work\Personal\Mix\Gradus
git remote add origin https://github.com/epochix/epochix.git
git push -u origin main
```

- On Windows, **Git Credential Manager** pops up a browser window the first
  time — click *Sign in with your browser*, authorize, done. It remembers
  afterwards.
- Expected output ends with `main -> main` and `branch 'main' set up to
  track 'origin/main'`.

### 1d. Watch the first CI run

1. Open `https://github.com/epochix/epochix/actions`.
2. A **CI** run appears within seconds. It contains: `lint`, `typecheck`,
   `test` (a 12-job matrix: Ubuntu/macOS/Windows × Python 3.10–3.13),
   `test-frontend`, `e2e`, `lighthouse`. A **Docs** run also starts (it
   builds the site; the deploy part is enabled in step 1e).
3. Wait for green (~5–10 min).
   - If `lighthouse` fails on a score threshold: it's advisory-quality, not
     packaging — note it and continue; everything else must be green.
   - Anything else red: copy the failing job's log into Claude.

### 1e. Repository settings

All under `https://github.com/epochix/epochix/settings`:

| # | Path | Action |
|---|---|---|
| 1 | **Pages** (left sidebar) → *Build and deployment* | **Source** dropdown → select **GitHub Actions** (not "Deploy from a branch"). No save button — it applies instantly. |
| 2 | **Advanced Security** (older UI: *Code security and analysis*) | Find **Private vulnerability reporting** → **Enable**. This is where SECURITY.md sends reporters. |
| 3 | *(optional but wise)* **Branches** → Add branch ruleset | Target `main`, tick *Require a pull request before merging* + *Require status checks to pass* once you start collaborating. Skip for solo work. |

After enabling Pages, re-run the **Docs** workflow (Actions → Docs → *Re-run
all jobs*) so the site actually deploys. It lands at
`https://epochix.github.io/epochix/`.

**Step 1 done when:** CI is green, docs URL loads, repo shows the README
with the logo.

---

## Step 2 — PyPI trusted publisher (~10 min)

No API tokens: `release.yml` authenticates to PyPI via OIDC ("trusted
publishing"). You just tell PyPI which repo+workflow to trust. Doing this
now also **reserves the `epochix` name** before the project exists.

### 2a. Account

1. Go to <https://pypi.org/account/register/> → username, email, password.
2. Verify the email (link arrives within a minute).
3. PyPI forces 2FA: **Account settings** → *Two factor authentication* →
   **Add 2FA with authenticator application** → scan the QR code with your
   authenticator app → enter the 6-digit code.
4. It then makes you generate **recovery codes** — store them in your
   password manager. You must confirm one to finish.

### 2b. Pending publisher

1. Go to <https://pypi.org/manage/account/publishing/>.
2. Scroll to **Add a new pending publisher** → **GitHub** tab.
3. Fill exactly:

   | Field | Value | Note |
   |---|---|---|
   | PyPI Project Name | `epochix` | if "already in use" → STOP, tell Claude — the PyPI name is taken and we rename again |
   | Owner | `epochix` | the GitHub org |
   | Repository name | `epochix` | |
   | Workflow name | `release.yml` | just the filename, no path |
   | Environment name | `pypi` | matches `environment: pypi` in the workflow — don't leave blank |

4. Click **Add**. It appears under "Pending publishers".

**Step 2 done when:** the pending publisher row is listed. The project page
itself won't exist until the first real release — that's normal.

---

## Step 3 — VS Code Marketplace publisher (~20 min)

The extension manifest says `"publisher": "epochix"`, so the publisher ID
must be **exactly** `epochix`. The Marketplace runs on Azure DevOps, hence
the Microsoft detour.

### 3a. Azure DevOps organisation

1. Go to <https://dev.azure.com> → **Start free** / *Sign in* with a
   Microsoft account (create one at <https://signup.live.com> if needed).
2. First login shows "Get started with Azure DevOps" → **Continue**. It
   auto-creates an organisation like `dev.azure.com/yourname` — the name is
   irrelevant, nobody sees it. If asked for a project name, enter anything
   (e.g. `placeholder`); it's unused.

### 3b. Personal Access Token (PAT)

1. In Azure DevOps, top-right: click the **user settings** icon (person
   with gear) → **Personal access tokens**.
2. **+ New Token**, then fill:

   | Field | Value | Gotcha |
   |---|---|---|
   | Name | `epochix-marketplace` | |
   | **Organization** | **All accessible organizations** | ← the #1 failure mode. If left on a single org, publishing fails with 401. |
   | Expiration | Custom defined → 1 year out | put a rotation reminder in your calendar |
   | Scopes | click **Show all scopes** (link at the bottom) → scroll to **Marketplace** → tick **Manage** | "Manage" implies acquire+publish |

3. **Create** → the token is displayed **once**. Copy it into your password
   manager immediately.

### 3c. Create the publisher

1. Go to <https://marketplace.visualstudio.com/manage> — sign in with the
   **same Microsoft account**.
2. **Create publisher**:
   - **ID:** `epochix` — immutable, must match the manifest.
     **If taken → STOP, tell Claude** (we'd change `"publisher"` in
     `epochix-vscode/package.json` + the Marketplace URLs before tagging).
   - **Display name:** `Epochix`
   - Fill the required fields; logo/description can be edited later
     (the extension carries its own icon).
3. **Create**.

### 3d. Store the token as a GitHub secret

1. `https://github.com/epochix/epochix/settings/secrets/actions` →
   **New repository secret**.
2. **Name:** `VSCE_PAT` (exact, case-sensitive) · **Secret:** the PAT from 3b
   → **Add secret**.

**Step 3 done when:** the publisher shows in your manage page and `VSCE_PAT`
is listed under Actions secrets (value hidden — that's normal).

---

## Step 4 — Open VSX publisher (~15 min, optional)

Open VSX serves VSCodium, Gitpod, Theia, Cursor-alikes. Cheap goodwill;
skip if you want (see the note at the end of this step).

1. Go to <https://open-vsx.org> → **Login** (top-right) → authorize with
   GitHub.
2. Publishing requires a signed **Eclipse Foundation publisher agreement**:
   - Click your avatar → **Settings**. If it says "Log in with Eclipse" /
     "Publisher Agreement missing":
   - Create an Eclipse account at <https://accounts.eclipse.org/user/register>
     — **important:** in the Eclipse profile, set the *GitHub username*
     field to `kv4u` (it links the accounts).
   - Back on open-vsx.org → Settings → sign the agreement (one click once
     the accounts are linked).
3. Token: avatar → **Settings** → **Access Tokens** → *Generate New Token*
   (name: `epochix-ci`) → copy it.
4. GitHub secret, same as 3d: name **`OVSX_PAT`**, value = the token.
5. Namespace: created automatically on first publish. For the "verified"
   badge, afterwards open a *namespace ownership* issue at
   <https://github.com/EclipseFdn/open-vsx.org/issues/new/choose>.

> **Skipping Open VSX?** Tell Claude to remove the `publish-openvsx` job
> from `.github/workflows/vscode-release.yml` (and its entry in
> `attach-release-asset.needs`) — otherwise every release shows one failed
> job for the missing secret.

---

## Step 5 — Docs domain (~5 min, or defer)

`docs.epochix.dev` is referenced in the README, `pyproject.toml` and
`mkdocs.yml`.

**Option A — own the domain.**
1. Buy `epochix.dev` at any registrar (Cloudflare / Porkbun / Namecheap;
   `.dev` costs ~$12/yr and is HTTPS-only by design — that's fine).
2. In the registrar's DNS panel add:
   `CNAME` · host/name `docs` · target `epochix.github.io` · TTL auto.
3. Repo → Settings → **Pages** → *Custom domain* → `docs.epochix.dev` →
   **Save**. Wait for the DNS check (minutes to ~1 h), then tick
   **Enforce HTTPS** once the certificate is issued.

**Option B — defer.** Docs already deploy to
`https://epochix.github.io/epochix/` with zero setup. If you stay on that
URL, tell Claude to replace the `docs.epochix.dev` references so the links
in the README/PyPI page aren't dead.

---

## Step 6 — Dry-run release (~10 min)

Prove the entire pipeline without publishing anything:

```powershell
cd C:\Work\Personal\Mix\Gradus
git tag test/v0.3.0
git push origin test/v0.3.0
```

What happens:

- `vscode-release.yml` runs **fully** — builds the frontend, packages the
  `.vsix`, type-checks — but **skips** the Marketplace/Open VSX publish
  steps for `test/` tags.
- `release.yml` also fires; its PyPI job will fail or wait on the `pypi`
  environment — expected for a dry-run tag, ignore it.

Final smoke test with the artifact:

1. Actions → the *VS Code Extension Release* run → **Artifacts** →
   download `vsix-0.3.0` → unzip → you have `epochix-0.3.0.vsix`.
2. VS Code → Extensions panel → `…` menu (top-right of the panel) →
   **Install from VSIX…** → pick the file.
3. `Ctrl+Alt+M` → the Epochix dashboard opens. Check the icon looks right
   in the Extensions list.

Clean up the tag:

```powershell
git push --delete origin test/v0.3.0
git tag -d test/v0.3.0
```

---

## Step 7 — The real release (~5 min + waiting)

```powershell
cd C:\Work\Personal\Mix\Gradus
git tag v0.3.0
git push origin v0.3.0
```

Both release workflows run in parallel:

| Workflow | Publishes |
|---|---|
| `release.yml` | wheel + sdist → **PyPI** (via the trusted publisher), SBOM → GitHub Release |
| `vscode-release.yml` | `.vsix` → **VS Code Marketplace** + **Open VSX**, `.vsix` → GitHub Release asset |

Marketplace listings take ~5–15 min to appear after the workflow finishes
(their side, not ours).

### Post-release verification checklist

```powershell
# Fresh-environment install test
py -3.13 -m venv $env:TEMP\epxcheck
& $env:TEMP\epxcheck\Scripts\Activate.ps1
pip install epochix
epochix demo          # → browser opens a populated dashboard
deactivate
```

- [ ] <https://pypi.org/project/epochix/> exists, README renders, version 0.3.0
- [ ] VS Code → Extensions → search "Epochix" → listing with logo → install
      → `Ctrl+Alt+M` works
- [ ] GitHub → Releases → v0.3.0 has `epochix-0.3.0.vsix` and
      `sbom.cyclonedx.json` attached
- [ ] README badges render (PyPI version, CI, Marketplace version)
- [ ] Docs URL loads (Pages or custom domain)

---

## Routine for future releases

1. Land changes on `main`; document them in `CHANGELOG.md` under a new
   version heading.
2. Bump `version` in **`pyproject.toml`** and **`frontend/package.json`**
   (the extension version is stamped from the tag automatically).
3. If any `package.json` changed, regenerate its lockfile — CI's `npm ci`
   fails on drift (this bit us in 0.3.0):
   ```powershell
   npm --prefix frontend install --package-lock-only
   npm --prefix epochix-vscode install --package-lock-only
   ```
4. Optionally dry-run with a `test/vX.Y.Z` tag.
5. `git tag vX.Y.Z && git push origin vX.Y.Z`. Done.

---

## Troubleshooting the first release

| Symptom | Likely cause | Fix |
|---|---|---|
| `git push` → 403 / auth loop | Credential Manager cached a wrong account | Windows Credential Manager → remove `git:https://github.com` entries → push again |
| PyPI job: "invalid-publisher" / OIDC error | Pending-publisher fields don't match | Re-check owner/repo/workflow/environment spelling on pypi.org — must be `epochix`/`epochix`/`release.yml`/`pypi` |
| `vsce publish` → 401 | PAT scoped to one org instead of **All accessible organizations**, or expired | Regenerate the PAT correctly, update the `VSCE_PAT` secret, re-run the job |
| `vsce publish` → publisher mismatch | Marketplace publisher ID ≠ `epochix` | The ID is immutable — if you created a different ID, tell Claude to change `"publisher"` in the manifest |
| Open VSX job fails, everything else fine | `OVSX_PAT` missing or agreement unsigned | Finish Step 4, re-run just that job — or remove the job if skipping Open VSX |
| Docs workflow green but no site | Pages source not set to GitHub Actions | Step 1e #1, then re-run the Docs workflow |

## Known deferred items (not release blockers)

- **Google Fonts** load from the CDN at dashboard runtime — a privacy /
  offline tradeoff. Self-hosting adds ~150 KB; revisit if users ask for
  air-gapped mode.
- `websockets.legacy` deprecation warning via uvicorn — upstream noise,
  disappears with a future uvicorn bump.
- Store write throughput is advisory (~6–10k writes/sec depending on
  hardware); revisit batching if live runs ever log faster than that.
