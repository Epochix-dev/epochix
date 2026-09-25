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

The PDF draws Farsi since 0.7.15. fpdf2's core fonts are Latin-1, and
localising the PDF on them initially made Farsi *worse* — headings, labels and
narrative all became question marks. A Farsi report now embeds Vazirmatn
(SIL Open Font License, shipped with the package, ~245 KB) and shapes its text
with uharfbuzz, so letters join and read right to left; right-to-left pages
align to the right. The shaper is in the `pdf` extra: without it a Farsi PDF
still falls back to English chrome and its cover says `pip install
"epochix[pdf]"`. Scripts beyond Latin and Arabic (CJK in a run name, say) still
degrade to the run id, as before.

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
