from __future__ import annotations

import contextlib
import json
import re
from statistics import fmean
from typing import cast

from epochix.models import RawMetric
from epochix.normalizer.canonical_keys import canonicalize_key
from epochix.parsers._never_metrics import NEVER_METRICS
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# Pattern 1: key=value
# Key capture is bounded ({1,64}) so a long run of word characters before a
# missing delimiter can't trigger O(n²) backtracking (a 100k-char line used to
# hang the parser for seconds). A real metric key is never that long.
_KV_EQ = re.compile(r"(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 2: key: value
_KV_COLON = re.compile(r"(\w{1,64})\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 3: JSON-ish dict anywhere in the line
_JSON_FRAG = re.compile(r"\{[^{}]+\}")
# Bare "Epoch N" / "Epoch N/M" header (common when the epoch is printed on the
# same line as the metrics, e.g. "Epoch 1/8: loss=…"). Digit runs bounded to
# stay linear. Captures the epoch and, when present, the total for the progress
# bar. This is NOT a key=value pair, so the KV patterns miss it otherwise.
_EPOCH_HEADER = re.compile(r"\bepoch\s+(\d{1,9})(?:\s*/\s*(\d{1,9}))?\b", re.IGNORECASE)

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# Pattern 4: "key value", separated by whitespace and nothing else.
#
#   epoch 1 loss 0.680 acc 0.535
#   iter 18 rmse 12.2614 r2 0.9960
#
# This is how a hand-written training loop usually prints, and it produced
# NOTHING: the patterns above all require a delimiter. Worse, the extension's
# detector scores "epoch … loss" as training with high confidence, so the
# dashboard opened itself and then sat empty.
#
# Applied under two guards, because a bare "word number" matches ordinary prose
# ("Done in 42.1s", "Train shape 60000") and inventing a metric is worse than
# missing one:
#   1. the line must open with an epoch/step counter, which is what makes it a
#      metric row rather than a sentence, and
#   2. the key must be a name the normalizer already recognises.
# Anything else still needs `=` or `:`.
_KV_SPACE = re.compile(rf"\b([A-Za-z][\w]{{0,63}})\s+({_NUM})(?=\s|$)")
_ROW_LEADER = re.compile(
    r"^\s*(?:epoch|ep|iter|iteration|step|batch|round)\s+\d{1,9}\b", re.IGNORECASE
)

# A whole-pass counter for code that has no epochs — sklearn's partial_fit
# loops, a boosting round, a hand-rolled solver. Used as the x-axis when the
# run never reports an epoch, so the story reads "at iteration 12" instead of
# "at epoch ?".
#
# Deliberately excludes `step` and `batch`: those count WITHIN an epoch, and a
# framework that prints "Step 500 …" before its first epoch line would
# otherwise have the run's epoch pinned to 500.
_ITERATION_LEADER = re.compile(r"^\s*(?:iter|iteration|round)\s+(\d{1,9})\b", re.IGNORECASE)

# Pattern 5: a qualifier in front of the metric — "Train accuracy: 0.98".
#
# `\w{1,64}` captures only the last word, so "Train accuracy" and "Test
# accuracy" both became `accuracy` and were charted as ONE two-point series
# running 1.0 → 0.982: a decline the model never had. They are measurements of
# different splits, not consecutive readings.
_QUALIFIED = re.compile(
    rf"\b(train|training|test|val|valid|validation|eval|holdout)\s+(\w{{1,64}})\s*[:=]\s*({_NUM})",
    re.IGNORECASE,
)
_VAL_WORDS = frozenset({"test", "val", "valid", "validation", "eval", "holdout"})

# Pattern 6: a two-word metric name — "F1 score: 0.98", "ROC AUC: 0.91",
# "R2 score: 0.87". `\w{1,64}` takes only the trailing word, so these were
# recorded as a metric called `score` and dropped into the shared custom
# bucket, where an F1 and an R² end up on one line together. Accepted only when
# the joined form is a name the normalizer knows, so ordinary prose ending in
# "something: 12" is still ignored.
#
# The first word must start with a letter. Allowing a digit let it span the
# gap in "Epoch 1/10 train_loss=0.5", pairing "10" with "train_loss" into the
# nonsense key "10_train_loss" — harmless only because unknown joins are
# discarded, and it left the real metric to be picked up by a later pattern.
_COMPOUND = re.compile(rf"\b([A-Za-z]\w{{0,31}})[\s_]+(\w{{1,32}})\s*[:=]\s*({_NUM})")

# A CamelCase constructor call and everything inside its parentheses:
#   RandomForestClassifier(n_estimators=100, max_depth=8, random_state=0)
#   Ridge(alpha=1.0)
#   Conv2d(3, 64, kernel_size=(3, 3))
#
# Those are the model's configuration, not measurements of it. Charting them
# put `max_depth=8` on the same series as an F1 of 0.9823 — a hyperparameter
# presented as a result. The existing _NN_REPR_KWARGS table fixed this for
# torch by listing every torch kwarg by name; scikit-learn, XGBoost and
# LightGBM have their own vocabularies, and enumerating all of them is a losing
# race. The shape is the reliable signal, so the region is masked out before
# any pattern above sees it.
_CONSTRUCTOR = re.compile(r"\b[A-Z]\w*\((?:[^()]|\([^()]*\))*\)")

# ── Cross-validation ───────────────────────────────────────────────────────
#
# A fold is a repeat, not a step. Charting five folds in the order they
# finished draws a line whose slope is pure noise — shuffle the data and it
# points the other way — and the printed mean was picked up as a sixth fold,
# mixing a summary into the series it summarises.
#
# Folds are collected instead and reduced to their mean when the stream ends.
# The spread is kept on the context so `epochix check` can report it, since the
# spread is the entire reason to cross-validate.
#
# Real shapes, captured from scikit-learn rather than remembered:
#   Fold 1: accuracy = 0.9375                                   (hand-written)
#   [CV] END .......... score: (test=0.938) total time=   0.0s  (cross_val_score)
#   [CV 1/3] END ......max_depth=3;, score=0.933 total time=    (GridSearchCV)
# The boundary belongs inside each alternative: `\b` after the closing "]" of
# "[CV]" never matches, because both sides of that position are non-word
# characters — so every scikit-learn CV row sailed straight past this.
_FOLD_ROW = re.compile(r"^\s*(?:\[cv(?:\s+\d+\s*/\s*\d+)?\]|fold\s+\d+\b)", re.IGNORECASE)

# The score on a fold row. GridSearchCV also prints the parameter set being
# tried ("max_depth=3"), which is configuration and not a measurement — taking
# only the score keeps a hyperparameter from being charted as a result, the
# same fault as an estimator repr.
_CV_SCORE = re.compile(
    rf"\bscore\s*[:=]\s*\(?\s*(?:test|train)?\s*=?\s*({_NUM})",
    re.IGNORECASE,
)

_EPOCH_KEYS = frozenset({"epoch", "ep", "e"})
_STEP_KEYS = frozenset({"step", "iter", "iteration", "batch"})
# Never charted as metrics. Beyond obvious run metadata these cover the keyword
# arguments in a torch `print(model)` dump — following our own `epochix check`
# advice to print the model used to inject kernel_size/in_features/... into the
# dashboard as a fake "custom" metric series next to real accuracy.
_NN_REPR_KWARGS = frozenset(
    {
        "kernel_size",
        "stride",
        "padding",
        "dilation",
        "groups",
        "ceil_mode",
        "in_features",
        "out_features",
        "in_channels",
        "out_channels",
        "bias",
        "num_features",
        "eps",
        "momentum",
        "affine",
        "track_running_stats",
        "inplace",
        "output_padding",
        "padding_mode",
        "num_embeddings",
        "embedding_dim",
        "hidden_size",
        "num_layers",
        "nhead",
        "dropout",
        "batch_first",
        "return_indices",
        "count_include_pad",
    }
)

# Run config, model-summary totals and units come from the shared table so the
# parsers cannot drift apart again.
_SKIP_KEYS = NEVER_METRICS | _NN_REPR_KWARGS

# tqdm / download progress bars ("Downloading: 100%|####| 26.4M/26.4M [00:03…]")
# yielded bogus "Downloading=100" and "00=3" metrics. Whole line is noise.
_PROGRESS_BAR = re.compile(r"\d{1,3}%\|")


@register_parser
class UniversalParser:
    name = "universal"
    priority = 1  # lowest — always a fallback

    def sniff(self, sample_lines: list[str]) -> float:  # noqa: ARG002
        return 0.10  # always weakly confident; format detector uses this as floor

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        if _PROGRESS_BAR.search(line):
            return []

        if _FOLD_ROW.match(line):
            self._collect_fold(line, ctx)
            return []
        # Bare epoch header ("Epoch 1/8: …") — set the epoch/total so metrics on
        # the same line are stamped with it and the progress bar advances.
        eh = _EPOCH_HEADER.search(line)
        if eh is not None:
            ctx.current_epoch = float(eh.group(1))
            if eh.group(2) is not None:
                ctx.total_epochs = int(eh.group(2))

        it = _ITERATION_LEADER.match(line)
        if it is not None and (ctx.current_epoch is None or ctx.extra.get("axis") == "iteration"):
            # Latched: the guard has to be "no epoch has EVER been seen", not
            # "no epoch right now". Checking only the latter pinned the whole
            # run to iteration 1, because after the first row current_epoch was
            # no longer None and every later row was ignored.
            ctx.extra["axis"] = "iteration"
            ctx.current_epoch = float(it.group(1))

        # Blank out model configuration before anything reads the line. Spaces,
        # so every span below still lines up with the original.
        text = _CONSTRUCTOR.sub(lambda m: " " * len(m.group()), line)

        # Collect every candidate first, in confidence order (JSON > key=value >
        # key: value), so the two passes below see the whole line.
        candidates: list[tuple[str, float, float]] = []

        # Split-qualified metrics first, and blanked once taken: otherwise the
        # colon pattern reads "Train accuracy: 0.98" a second time as a bare
        # `accuracy`, and one printed number becomes two recorded measurements.
        def _blank(match: re.Match[str]) -> str:
            return " " * len(match.group())

        for q in _QUALIFIED.finditer(text):
            split = q.group(1).lower()
            split = "val" if split in _VAL_WORDS else "train"
            with contextlib.suppress(ValueError):
                candidates.append((f"{split}_{q.group(2)}", float(q.group(3)), 0.60))
        text = _QUALIFIED.sub(_blank, text)

        for c in _COMPOUND.finditer(text):
            joined = f"{c.group(1)}_{c.group(2)}"
            if canonicalize_key(joined) == "custom":
                continue
            with contextlib.suppress(ValueError):
                candidates.append((joined, float(c.group(3)), 0.58))
            text = text[: c.start()] + " " * len(c.group()) + text[c.end() :]

        for frag in _JSON_FRAG.finditer(text):
            frag_text = frag.group().replace("'", '"')
            try:
                obj: dict[str, object] = json.loads(frag_text)
            except json.JSONDecodeError:
                continue
            for k, v in obj.items():
                if isinstance(v, (int, float)):
                    candidates.append((k, float(v), 0.65))
        text = _JSON_FRAG.sub(_blank, text)

        for m in _KV_EQ.finditer(text):
            with contextlib.suppress(ValueError):
                candidates.append((m.group(1), float(m.group(2)), 0.55))
        text = _KV_EQ.sub(_blank, text)

        for m in _KV_COLON.finditer(text):
            with contextlib.suppress(ValueError):
                candidates.append((m.group(1), float(m.group(2)), 0.45))
        text = _KV_COLON.sub(_blank, text)

        # Whitespace-separated pairs, last and only on a metric row (see
        # _KV_SPACE). Everything a delimiter already claimed has been blanked
        # out above, so this cannot double-count a reading.
        if _ROW_LEADER.match(line):
            for m in _KV_SPACE.finditer(text):
                key = m.group(1)
                key_lo = key.lower()
                # Recognised metric, or a control key we need for the x-axis.
                if (
                    key_lo not in _EPOCH_KEYS
                    and key_lo not in _STEP_KEYS
                    and canonicalize_key(key) == "custom"
                ):
                    continue
                with contextlib.suppress(ValueError):
                    candidates.append((key, float(m.group(2)), 0.50))

        # Pass 1 — control keys (epoch/step) take effect BEFORE any metric on
        # this line is stamped. They can legitimately appear last: the SDK
        # serialises log(**kwargs) in call order, and frameworks emit e.g.
        # "loss=0.3 … epoch=3". Stamping as we scanned would have attributed
        # those metrics to the *previous* epoch (and dropped the first epoch
        # entirely, as epoch=None).
        claimed: set[str] = set()
        for key, val, _conf in candidates:
            key_lo = key.lower()
            if key_lo in claimed:
                continue
            if key_lo in _EPOCH_KEYS:
                claimed.add(key_lo)
                ctx.current_epoch = val
            elif key_lo in _STEP_KEYS:
                claimed.add(key_lo)
                ctx.current_step = int(val)

        # Pass 2 — emit the metrics; first occurrence of a key wins.
        metrics: list[RawMetric] = []
        seen_keys: set[str] = set()
        for key, val, conf in candidates:
            key_lo = key.lower()
            if (
                key_lo in seen_keys
                or key_lo in _SKIP_KEYS
                or key_lo in _EPOCH_KEYS
                or key_lo in _STEP_KEYS
            ):
                continue
            seen_keys.add(key_lo)
            # Remembered so a printed mean is not duplicated by the fold
            # aggregate at flush time (see flush).
            emitted: set[str] = ctx.extra.setdefault("emitted_keys", set())  # type: ignore[assignment]
            emitted.add(key_lo)
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=val,
                    parser_name=self.name,
                    confidence=conf,
                )
            )

        return metrics

    def _collect_fold(self, line: str, ctx: ParserContext) -> None:
        """Record one cross-validation fold without emitting it as a point."""
        folds: dict[str, list[float]] = ctx.extra.setdefault("cv_folds", {})  # type: ignore[assignment]

        score = _CV_SCORE.search(line)
        if score is not None:
            # A named score wins outright. GridSearchCV prints the candidate's
            # parameters on the same row ("max_depth=3;, score=0.933"), and
            # those are settings, not measurements.
            with contextlib.suppress(ValueError):
                folds.setdefault("score", []).append(float(score.group(1)))
            return

        # A hand-written loop names the metric instead: "Fold 1: accuracy = 0.9375".
        for pattern in (_KV_EQ, _KV_COLON):
            hits = 0
            for match in pattern.finditer(line):
                key = match.group(1)
                key_lo = key.lower()
                if key_lo in _SKIP_KEYS or key_lo in _EPOCH_KEYS or key_lo in _STEP_KEYS:
                    continue
                with contextlib.suppress(ValueError):
                    folds.setdefault(key, []).append(float(match.group(2)))
                    hits += 1
            if hits:
                return

    def flush(self, ctx: ParserContext) -> list[RawMetric]:
        """Reduce collected cross-validation folds to one value per metric.

        Called once the stream ends. A fold set becomes its mean — the result
        cross-validation actually reports — rather than a run of points whose
        order carries no meaning.

        A metric the log printed its own mean for is skipped: emitting the
        aggregate as well would put two points on a chart that has no trend at
        all, which is the shape this exists to avoid.
        """
        # ctx.extra is a dict[str, object] bag shared by every parser, so what
        # comes back out has to be narrowed explicitly.
        folds = cast("dict[str, list[float]]", ctx.extra.get("cv_folds") or {})
        emitted = cast("set[str]", ctx.extra.get("emitted_keys") or set())

        out: list[RawMetric] = []
        for key, values in folds.items():
            if len(values) < 2 or key.lower() in emitted:
                continue
            out.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=None,
                    step=None,
                    key=key,
                    value=fmean(values),
                    parser_name=self.name,
                    confidence=0.5,
                )
            )
        return out
