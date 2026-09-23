#!/usr/bin/env python
"""Land a Dependabot PR as an ordinary commit by the maintainer.

    python scripts/land_dependabot.py 53
    make land PR=53

Why this exists: GitHub's Contributors list is built from the commit AUTHORS on
the default branch, and a squash merge made in the GitHub UI (or with
`gh pr merge --squash`) keeps `dependabot[bot]` as the author and adds
`Co-authored-by` / `Signed-off-by` trailers for it. Thirty-one merged
Dependabot PRs put "dependabot[bot]" on this project's contributor list.
There is no repository setting that changes the author of a squash merge, so
the merge is done here instead: same change, authored by whoever is configured
in git, no bot trailers, and the PR is closed with a pointer to the commit.

It refuses to land anything that CI has not tested AS IT WILL LAND. `main` is
not branch-protected, so a direct push skips the PR gate entirely; the checks
below are that gate. In particular a PR whose base is behind `main` is refused
and Dependabot is asked to rebase, because its green checks describe a merge
result that no longer exists — merging stale codeql-action PRs one at a time
once left `main` red.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

BOT = "dependabot[bot]"
GH = "gh"


def run(*cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        raise SystemExit(f"$ {' '.join(cmd)}\n{result.stdout}{result.stderr}".rstrip())
    return result.stdout.strip()


def git(*args: str, check: bool = True) -> str:
    return run("git", *args, check=check)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pr", type=int, help="the Dependabot pull request number")
    parser.add_argument("--gh", default=GH, help="path to the gh executable")
    parser.add_argument(
        "--dry-run", action="store_true", help="check and build the commit, but do not push"
    )
    args = parser.parse_args(argv)
    gh = args.gh

    pr = json.loads(
        run(gh, "pr", "view", str(args.pr), "--json",
            "number,title,state,author,headRefName,headRefOid,baseRefName,url")
    )
    if pr["author"]["login"] not in {BOT, "app/dependabot"}:
        raise SystemExit(f"#{args.pr} is by {pr['author']['login']}, not Dependabot")
    if pr["state"] != "OPEN":
        raise SystemExit(f"#{args.pr} is {pr['state']}")
    if pr["baseRefName"] != "main":
        raise SystemExit(f"#{args.pr} targets {pr['baseRefName']}, not main")

    checks = json.loads(run(gh, "pr", "checks", str(args.pr), "--json", "name,state"))
    failing = [c["name"] for c in checks if c["state"] not in {"SUCCESS", "SKIPPED", "NEUTRAL"}]
    if not checks or failing:
        raise SystemExit(f"#{args.pr} is not green: {failing or 'no checks reported'}")

    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("working tree has uncommitted changes")
    git("fetch", "--quiet", "origin", "main", pr["headRefName"])
    head = git("rev-parse", f"origin/{pr['headRefName']}")
    if head != pr["headRefOid"]:
        raise SystemExit(f"#{args.pr} moved while checking; run again")

    # Tested as it will land? Only if the PR already contains current main.
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", "origin/main", head]
    ).returncode != 0:
        run(gh, "pr", "comment", str(args.pr), "--body", "@dependabot rebase")
        print(f"#{args.pr} is behind main; asked Dependabot to rebase. Re-run once CI is green.")
        return 2

    git("checkout", "--quiet", "main")
    git("merge", "--quiet", "--ff-only", "origin/main")
    git("merge", "--squash", "--quiet", head)
    if not git("diff", "--cached", "--name-only"):
        git("reset", "--quiet", "--hard", "origin/main")
        raise SystemExit(f"#{args.pr} changes nothing on main")

    author = git("config", "user.name")
    if not author or "dependabot" in author.lower():
        git("reset", "--quiet", "--hard", "origin/main")
        raise SystemExit(f"refusing to commit as {author!r}")

    message = (
        f"{pr['title']} (#{args.pr})\n\n"
        f"Landed from Dependabot PR #{args.pr}, whose CI passed on a base that\n"
        f"already contained main. Committed directly rather than squash-merged\n"
        f"on GitHub, which would record dependabot[bot] as the author.\n"
    )
    git("commit", "--quiet", "-m", message)
    sha = git("rev-parse", "--short", "HEAD")

    if args.dry_run:
        print(f"dry run: built {sha}; resetting main to origin/main")
        git("reset", "--quiet", "--hard", "origin/main")
        return 0

    git("push", "--quiet", "origin", "main")
    run(
        gh, "pr", "close", str(args.pr), "--delete-branch", "--comment",
        f"Landed on main as {sha}, authored by the maintainer rather than squash-merged, "
        f"so the commit is not attributed to dependabot[bot]. The dependency change is "
        f"identical.",
    )
    print(f"#{args.pr} landed as {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
