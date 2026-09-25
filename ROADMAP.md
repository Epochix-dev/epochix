# Roadmap

Open work, roughly in the order it is worth doing. Each item says what is
actually wrong and how it was measured, so nobody has to rediscover it.

Closed items live in [CHANGELOG.md](CHANGELOG.md).

---

## Blocked — not on us

- **Verify activation capture on Apple MPS / AMD ROCm.** There is no
  vendor-specific code and no device gating; capture uses PyTorch and Keras
  forward hooks, and it has been proven to work with every accelerator hidden.
  So it *should* work — but it has only been run on CUDA and CPU, and untested
  is not the same as supported. `epochix doctor` prints the result on whatever
  device it finds and asks for that line on an unverified backend. Needs
  hardware we do not have.
- **VS Code Marketplace verified publisher.** Eligibility opens around
  January 2027.

---

## PDF export

Done, including the last two gaps: a run whose only series is a metric we do
not recognise by name — a GridSearchCV score, typically — now gets its own
panel, charted under its own name, instead of reaching no curve at all, and a model deeper than one page continues onto
another rather than stopping at the page edge with the rest reported as a
count.

## Internationalisation

Complete for the three locales the project ships. Narratives (54/54 template
groups), warning and milestone messages, dashboard UI (54/54 keys, none
unused — a test fails on a dead or missing key), the CLI, the exports and the
VS Code extension's own engine all speak English, Farsi and French.

What was wrong and is now fixed: the CLI had **no `--locale` flag at all**, so
the translations existed and the primary interface could not reach them; the
locale was **never stored on the run**, so nothing downstream could know what
language a report should be in; and **no exporter took a locale**, so a Farsi
run's sentences came out Farsi with every heading around them in English.

Verified end to end across all three locales and every export format: a
standalone HTML export now opens with `lang`, `dir` and its UI in the run's
language (this was broken — the locale was read only from `?locale=` and
localStorage, neither of which a file on disk has, so every export fell back
to English chrome around Farsi sentences).

One limitation remains, and it is stated rather than hidden:

- **The PDF cannot draw Persian.** fpdf2's core fonts are Latin-1. Localising
  the PDF initially made Farsi *worse* — headings, labels and narrative all
  became question marks, so even the structure stopped being navigable. It now
  detects an undrawable locale, falls back to English chrome, and says so on
  the cover, pointing at the HTML and Markdown exports, which carry Farsi
  perfectly. Embedding a font remains rejected on the grounds recorded below.

## Dashboard

Two of the three items here were **wrong**, and are corrected rather than
quietly dropped:

- *"The layout is locked to one screen."* It is not. `#app` is a fixed-height
  shell and `.app-body` scrolls inside it (`overflow-y: auto`) — measured live
  at **3510px of content in a 720px region**, about five screens. The original
  claim came from reading `document.scrollHeight === innerHeight`, which is
  simply how an app shell behaves, in a browser pane that was reporting a
  viewport of 0x0 at the time.
- *"Milestone surfaces are unreachable."* Milestones are rendered by
  `TimelineStory`, mounted through `JourneyPanel`. The run I probed had zero
  milestones, so the DOM was empty for a legitimate reason.

What was real:

- `ImprovementWaterfall` and `ParticleField` had **no importer at all** —
  211 lines of dead module, one of them referenced only in a comment. Deleted.
- **Warnings were computed and never shown.** Fixed — see the changelog.

- **The headline story contradicted the warning beside it.** The same
  overfitting run that triggered the memorisation warning was narrated as
  "not learning yet — check the learning rate". Found by reading the rendered
  page, not the tests: both statements were on screen at once. Fixed — see
  the changelog.

## Audit of the week's changes (2026-09-02)

Eight real log shapes × five export formats × three locales, 114 artefacts,
read rather than merely produced. Six defects, every one of the same shape:
renders fine, exits 0, states something the data denies. See the 0.7.7
changelog. The two that generalise:

- A task is chosen from the metric NAMES in a log; the primary metric is the
  first PREFERRED key actually seen. Those two disagree routinely, and every
  template set that names its metric in the prose was wrong whenever they did.
- A metric whose direction is not pinned inherits its task's default, and the
  failure is silent — the grade simply comes out inverted. Tests now assert
  the direction of every preferred key, and that no key can classify a run it
  cannot then narrate.

Follow-up (0.7.8): the abrupt-NaN case the audit left open is closed. A run
whose loss jumps straight to `nan` now ends with a divergence frame instead of
keeping the grade it earned before it blew up. Fixing it surfaced a second
defect one layer up — a frame with no metaphor cards left the previous frame's
cards on screen, so the diverged run displayed "Grade B+" beside its "Grade F".

## A test that validated the wrong artifact (2026-09-23)

0.7.5 through 0.7.10 shipped a blank standalone panel in the VS Code
extension, introduced by a 0.7.5 change of mine and caught only by unpacking
the published `.vsix`. The lesson generalises beyond this bug: **the extension
tests were run against `frontend/dist` (the server build), but the release
packages `build:webview` output.** Two builds, one tested, the other shipped.
Now CI builds what the release builds and packages the `.vsix` itself. When a
release step rebuilds something (`vscode:prepublish`), test the rebuild.

## Dependabot on the Contributors list (2026-09-23)

GitHub builds the Contributors list from commit authors on `main`, and a squash
merge in the GitHub UI keeps `dependabot[bot]` as the author (plus
`Co-authored-by` / `Signed-off-by` trailers). 31 merged Dependabot PRs put it on
the list. There is no repository setting that changes a squash merge's author.

**Land Dependabot PRs with `make land PR=<n>`, never the GitHub merge button.**
It commits the same change as the maintainer and closes the PR, and it refuses
any PR whose CI did not run on a base containing current `main` — `main` is not
branch-protected, so that check is the only gate a direct push has.

The 31 existing bot-authored commits were re-authored on 2026-09-23 by
rewriting `main` (user-approved; trees verified identical commit by commit;
tags left on the original commits; backup branch
`backup/main-before-reauthor-2026-09-23`). The Contributors API now lists only
the maintainer.

Security settings enabled the same day: Dependabot security updates, secret
scanning and push protection (vulnerability alerts were already on). The
initial secret scan of the full history found nothing. Security-update PRs are
opened by Dependabot too — land them with `make land` like any other.

## Engine parity (2026-09-24)

The extension's TypeScript engine was brought up to the Python engine's
truthfulness fixes in 0.7.12, and `standaloneTruthfulness.test.ts` drives it
through the same log shapes. Known gaps that remain, deliberately not done yet:

- ~~**Narratives are English only** in the extension engine.~~ Fixed in 0.7.13:
  templates, warning and milestone messages are generated from the Python
  engine in every locale.
- ~~**Regression keys lose their split** in the TS canonicaliser.~~ Fixed in
  0.7.13, with a wider cause: the TS name tables had drifted on 170 of 319 names.
- The name tables (canonical keys, task signals, preferred and on-scale keys)
  are **generated from the Python engine** since 0.7.13 (`make gen-ts-tables`),
  with a golden file replayed by the extension's tests, and so are the
  narrative templates and messages. Grading, direction and phase logic are
  still hand-ported; the tests on each side guard them.

## Parser parity (2026-09-25) — done in 0.7.14

Both engines are held to one truth file, `tests/fixtures/corpus_truth.json`
(38 logs: task, story metric, frames, last value, metric names, the epoch the
story's metric starts at), by `test_log_corpus_truth.py` and
`corpusParity.test.ts`. Before: 25 of 38 disagreed. After: 0. Name tables,
templates, messages and never-metric names are generated from Python; the
parsers and engine logic are ported, and this corpus is what keeps them honest.
Add a log to `demo/` or `tests/fixtures/logs/` and both tests fail until it has
an expectation.

## Performance (2026-09-24)

- **Universal parser throughput: ~25k lines/sec on CI, target 50k.** The
  benchmark gate never ran until 0.7.13 touched the parsers; it then measured
  16.7k. A single-scan rewrite (output byte-identical over 644k lines) took it
  to 25k, and the gate's floor for this parser is 20k meanwhile. The framework
  parsers clear 50k (64k-129k). Reaching 50k needs a different structure —
  one tokenising pass instead of eight patterns per line.

## Features worth considering

- **Run comparison in exports.** `CompareView` exists on screen and no export
  format includes it, so the one artifact you would want to send someone —
  "these two runs, side by side" — cannot leave the browser.
- **Say what to do next.** The engine already detects past-peak, stalled and
  overfitting. It describes them and stops short of the obvious next sentence:
  stop earlier, lower the learning rate, get more data.
- **Confidence in the grade for short runs.** An 11-epoch run and a 200-epoch
  run currently receive equally confident letters.
- **Separate GridSearchCV candidates properly.** Fold results are grouped by
  parameter set and the winner is charted, but `epochix check` reports
  "N candidates x M folds" without per-candidate detail in exports.
