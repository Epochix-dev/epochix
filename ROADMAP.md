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

Done. What was a five-page leaflet of four text lines per page is now a report:
curves (loss / quality / error), a cover carrying the evidence for its grade,
an epoch table with per-epoch change and the best row marked, a final-metrics
table with best-and-change per series, the skill bars, the model's layers with
a parameter total, and phase pages that state the span they cover and what the
metric did across it. Localised, and it degrades honestly where the fonts
cannot draw a language.

Remaining, small:

- **A GridSearchCV run charts nothing.** Its score canonicalises to `custom`,
  which is in none of the chart key groups, so the one number the search
  produced never reaches a curve.
- **A model longer than one page is truncated in the layer table.** The
  parameter total counts every layer and the row list says "(+N more)", but
  there is no continuation page as the epoch table has.

## Internationalisation

Complete for the three locales the project ships. Narratives (54/54 template
groups), dashboard UI (60/60 keys), the CLI, and the exports all speak English,
Farsi and French.

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

- **The layout is locked to one screen.** Measured live:
  `document.scrollHeight === window.innerHeight` (720 = 720). Fifteen
  visualisation modules compete for a single viewport, which is why charts are
  190px tall and the whole thing reads as thinner than it is. Letting the page
  scroll would give the existing panels room without building anything new.
- **Three modules appear unreachable** — `ImprovementWaterfall`,
  `ParticleField`, and the milestone/warning surfaces returned no DOM match on
  a real run. Either mount them or delete them; a dead panel is worse than no
  panel.

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
