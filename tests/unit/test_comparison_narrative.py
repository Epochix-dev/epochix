"""Explaining why one run beat another.

Overlaying two curves is what every tool does. Saying what the overlay *means*
is the part that is ours — and the part where it is easiest to state something
untrue, so the honesty rules get more tests than the happy path.
"""

from __future__ import annotations

import re

from epochix.story_engine.comparison import RunTrajectory, narrate_comparison

# Peaks at epoch 7 (0.865) then overfits down to 0.846.
OVERFIT = RunTrajectory(
    "run-A",
    "val_accuracy",
    [
        (1, 0.62),
        (2, 0.74),
        (3, 0.80),
        (4, 0.835),
        (5, 0.851),
        (6, 0.860),
        (7, 0.865),
        (8, 0.861),
        (9, 0.857),
        (10, 0.852),
        (11, 0.849),
        (12, 0.846),
    ],
)
# Climbs the whole way and is still climbing at the end.
HEALTHY = RunTrajectory(
    "run-B",
    "val_accuracy",
    [
        (1, 0.60),
        (2, 0.73),
        (3, 0.81),
        (4, 0.848),
        (5, 0.862),
        (6, 0.871),
        (7, 0.878),
        (8, 0.883),
        (9, 0.887),
        (10, 0.891),
        (11, 0.894),
        (12, 0.897),
    ],
)


def test_it_names_the_winner_and_both_values() -> None:
    text = narrate_comparison([OVERFIT, HEALTHY])
    assert "run-B" in text and "run-A" in text
    assert "0.8970" in text and "0.8460" in text


def test_it_explains_the_loser_went_past_its_peak() -> None:
    """The whole point: not that B won, but why A lost."""
    text = narrate_comparison([OVERFIT, HEALTHY])
    assert "peaked" in text.lower()
    assert "0.8650" in text, "did not name the value it peaked at"
    assert "epoch 7" in text, "did not name the epoch it peaked at"


def test_it_offers_the_counterfactual() -> None:
    """If A had stopped at its best, the gap would be 0.032 rather than 0.051."""
    text = narrate_comparison([OVERFIT, HEALTHY])
    assert "0.0320" in text and "0.0510" in text


def test_it_flags_a_winner_that_had_not_finished_improving() -> None:
    text = narrate_comparison([OVERFIT, HEALTHY])
    assert "still improving" in text.lower()


# ── the honesty rules ────────────────────────────────────────────────────────


def test_a_difference_inside_the_noise_is_not_a_winner() -> None:
    """Two seeds of one config land slightly apart. That is not a result."""
    a = RunTrajectory(
        "seed-1",
        "val_accuracy",
        [(i, 0.80 + 0.01 * i + (0.004 if i % 2 else -0.004)) for i in range(1, 11)],
    )
    b = RunTrajectory(
        "seed-2",
        "val_accuracy",
        [(i, 0.80 + 0.01 * i + (-0.003 if i % 2 else 0.003)) for i in range(1, 11)],
    )
    text = narrate_comparison([a, b]).lower()
    assert "no meaningful difference" in text
    assert "ahead of" not in text, "declared a winner inside the noise"


def test_runs_measuring_different_things_are_refused() -> None:
    gaze = RunTrajectory("gaze", "MAE", [(1, 7.0), (2, 5.1), (3, 4.2)])
    text = narrate_comparison([OVERFIT, gaze]).lower()
    assert "not comparable" in text
    assert "ahead of" not in text


def test_lower_is_better_metrics_pick_the_right_winner() -> None:
    a = RunTrajectory("loss-A", "val_loss", [(1, 0.9), (2, 0.6), (3, 0.45), (4, 0.40), (5, 0.38)])
    b = RunTrajectory("loss-B", "val_loss", [(1, 0.9), (2, 0.55), (3, 0.34), (4, 0.26), (5, 0.21)])
    text = narrate_comparison([a, b])
    assert text.startswith("loss-B"), f"picked the wrong winner: {text}"


def test_too_little_data_says_so() -> None:
    thin = RunTrajectory("thin", "val_accuracy", [(1, 0.5)])
    assert "not enough" in narrate_comparison([thin, OVERFIT]).lower()


def test_it_never_claims_a_cause() -> None:
    """It reports what the curves did. It must not assert why, in the causal
    sense — no learning rate or hyperparameter is being blamed."""
    text = narrate_comparison([OVERFIT, HEALTHY]).lower()
    for forbidden in ("because of", "caused by", "due to the learning rate"):
        assert forbidden not in text, f"claimed causation: {text}"


# ── localisation ─────────────────────────────────────────────────────────────


def test_it_is_localised() -> None:
    fa = narrate_comparison([OVERFIT, HEALTHY], locale="fa")
    assert re.search(r"[؀-ۿ]", fa), fa
    assert "0.8970" in fa, "numbers were lost in translation"

    fr = narrate_comparison([OVERFIT, HEALTHY], locale="fr")
    assert "devant" in fr, fr


def test_every_template_keeps_its_placeholders() -> None:
    """A translation that invents or drops a placeholder breaks one locale
    silently — English tests would never see it."""
    from pathlib import Path

    root = Path("src/epochix/story_engine/templates")
    for english in sorted(root.glob("_compare_*.txt")):
        if english.name.count(".") > 1:  # a localised variant
            continue
        expected = set(re.findall(r"\{(\w+)\}", english.read_text(encoding="utf-8")))
        for locale in ("fa", "fr"):
            localised = root / f"{english.stem}.{locale}.txt"
            if not localised.exists():
                continue  # falls back to English, which is fine
            found = set(re.findall(r"\{(\w+)\}", localised.read_text(encoding="utf-8")))
            assert found == expected, f"{localised.name}: {found} != {expected}"
