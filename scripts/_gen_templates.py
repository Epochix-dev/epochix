"""Generate all narrative template files under src/epochix/story_engine/templates/."""
from pathlib import Path

BASE = Path(__file__).parent.parent / "src" / "epochix" / "story_engine" / "templates"

TEMPLATES: dict[str, dict[str, list[str]]] = {
    # ── CLASSIFICATION ────────────────────────────────────────────────────────
    "classification": {
        "awakening": [
            "The model stirs to life at epoch {epoch}. Accuracy is {value_pct} — the journey of a thousand epochs begins with a single gradient.",
            "First patterns emerge from the noise. At {value_pct} accuracy, the model is learning to see.",
            "Epoch {epoch}: neurons fire for the first time. The baseline is set at {value_pct} accuracy — only one direction from here.",
            "The model awakens, uncertain but ready. Accuracy {value_pct}. Every weight is an open question.",
        ],
        "learning": [
            "Gradients flow, features sharpen. Accuracy climbs to {value_pct} — the model is finding the signal in the noise.",
            "At epoch {epoch}, patterns crystallise. The delta this step was {delta}. The upward trend is clear.",
            "The model discovers structure in its world. Accuracy {value_pct}, improving steadily. Keep going.",
            "Loss curves bend downward. Accuracy reaches {value_pct} at epoch {epoch}. The model is a diligent student.",
        ],
        "understanding": [
            "Deep representations form. Accuracy {value_pct} at epoch {epoch} — the model grasps the underlying structure.",
            "Generalisation improves. The gap between train and val narrows. Accuracy: {value_pct}.",
            "The model has moved beyond memorisation. At {value_pct}, it understands the task.",
            "Epoch {epoch}: high-level features emerge. The model reads the data, not just the surface. Accuracy {value_pct}.",
        ],
        "mastering": [
            "Near-expert performance at {value_pct}. Epoch {epoch} — the model has mastered the fundamentals.",
            "Fine boundaries sharpen. At {value_pct} accuracy, the model operates with confidence and precision.",
            "The model has internalised the task. Accuracy {value_pct}. Only refinement remains.",
            "Epoch {epoch}: the model thinks like an expert. Accuracy {value_pct}, delta {delta}.",
        ],
        "polishing": [
            "Polishing to {value_pct}. Final refinements bring the model to peak form. Epoch {epoch}.",
            "The last percentages are the hardest. At {value_pct}, the model approaches its ceiling.",
            "Excellence achieved. Accuracy {value_pct} — a model ready for the world.",
            "Epoch {epoch}: every adjustment is deliberate. The model is {value_pct} accurate and ready to ship.",
        ],
    },
    # ── DETECTION ─────────────────────────────────────────────────────────────
    "detection": {
        "awakening": [
            "Anchors scatter randomly at epoch {epoch}. mAP50 {value_pct} — the detector has yet to learn what a box means.",
            "The model sees the image but not the objects. mAP50 {value_pct}. Every anchor is a guess.",
            "Epoch {epoch}: bounding boxes drift without purpose. mAP50 {value_pct}. The grid is awakening.",
            "Detection begins at epoch {epoch}. mAP50 {value_pct} — confidence maps are learning to focus.",
        ],
        "learning": [
            "Boxes tighten around objects. mAP50 reaches {value_pct} at epoch {epoch}. The detector is learning to see.",
            "Recall climbs as anchors find their footing. mAP50 {value_pct}. The model learns object shape.",
            "At epoch {epoch}, the detector discovers scale. mAP50 {value_pct}, delta {delta}.",
            "Precision and recall dance toward balance. mAP50 {value_pct} and rising.",
        ],
        "understanding": [
            "Objects snap into focus. mAP50 {value_pct} at epoch {epoch} — the model understands what it seeks.",
            "Class boundaries sharpen. mAP50 {value_pct}. The model distinguishes car from bicycle, cat from dog.",
            "Epoch {epoch}: NMS clears the clutter. mAP50 {value_pct} — clean detections emerge.",
            "The model reads the scene. mAP50 {value_pct}. Confidence scores grow meaningful.",
        ],
        "mastering": [
            "Precise localisation at mAP50 {value_pct}. Epoch {epoch} — the detector operates with surgical accuracy.",
            "Small objects emerge from background. mAP50 {value_pct}. The model finds what the eye might miss.",
            "Epoch {epoch}: bounding boxes are tight and confident. mAP50 {value_pct}.",
            "Competition-grade performance approaches. mAP50 {value_pct}, delta {delta}.",
        ],
        "polishing": [
            "Final calibration. mAP50 {value_pct} at epoch {epoch} — the detector is ready for deployment.",
            "The last mAP points are won by patience. mAP50 {value_pct}. Excellence refined.",
            "Epoch {epoch}: detection is robust across scales and occlusions. mAP50 {value_pct}.",
            "The model sees all. mAP50 {value_pct} — every anchor finds its object.",
        ],
    },
    # ── REGRESSION ────────────────────────────────────────────────────────────
    "regression": {
        "awakening": [
            "The model guesses blindly. MAE {value} at epoch {epoch} — the distance between prediction and truth is vast.",
            "Epoch {epoch}: error is high at MAE {value}. The regression surface is flat and uninformed.",
            "The model knows nothing yet. MAE {value}. The gradient will guide it from here.",
            "Random predictions define epoch {epoch}. MAE {value}. The model has nowhere to go but down.",
        ],
        "learning": [
            "Error falls steadily. MAE {value} at epoch {epoch} — the regression surface bends toward truth.",
            "Predictions begin to track the target. MAE {value}, delta {delta}.",
            "At epoch {epoch}, the model finds coarse structure. MAE {value} and falling.",
            "The curve of error tilts downward. MAE {value}. Momentum builds.",
        ],
        "understanding": [
            "Predictions shadow reality. MAE {value} at epoch {epoch} — the model grasps the underlying mapping.",
            "Fine-grained patterns emerge. MAE {value}. The model interpolates with confidence.",
            "Epoch {epoch}: residuals shrink. MAE {value} — nonlinear structure is captured.",
            "The function approximator finds its shape. MAE {value}, delta {delta}.",
        ],
        "mastering": [
            "Tight predictions at MAE {value}. Epoch {epoch} — the regression model operates with precision.",
            "Outliers shrink. MAE {value}. The model handles edge cases with grace.",
            "Epoch {epoch}: the prediction surface matches the target manifold. MAE {value}.",
            "Near-perfect approximation. MAE {value}, delta {delta}.",
        ],
        "polishing": [
            "Last refinements at MAE {value}. Epoch {epoch} — the model squeezes residual error.",
            "The final decimal places are the hardest. MAE {value}. The model is near its capacity.",
            "Epoch {epoch}: prediction uncertainty is minimal. MAE {value} — ready to deploy.",
            "Excellence. MAE {value} at epoch {epoch}. The regressor has found its form.",
        ],
    },
    # ── BIOMETRIC ─────────────────────────────────────────────────────────────
    "biometric": {
        "awakening": [
            "The identity model is blind at epoch {epoch}. EER {value_pct} — genuine and impostor are indistinguishable.",
            "All faces look alike. EER {value_pct} at epoch {epoch}. The model has yet to learn identity.",
            "Epoch {epoch}: feature space is undifferentiated. EER {value_pct}. The journey to recognition begins.",
            "The model sees faces but not people. EER {value_pct}. Random is the baseline.",
        ],
        "learning": [
            "Faces begin to separate. EER falls to {value_pct} at epoch {epoch}. Identity clusters form.",
            "The model learns that two photos of the same person share something. EER {value_pct}.",
            "Epoch {epoch}: intra-class variance shrinks. EER {value_pct}, delta {delta}.",
            "Genuine pairs pull together, impostors push apart. EER {value_pct} and falling.",
        ],
        "understanding": [
            "Identity representations stabilise. EER {value_pct} at epoch {epoch} — the model knows a face.",
            "The embedding space separates identity clusters cleanly. EER {value_pct}.",
            "Epoch {epoch}: the model distinguishes similar individuals by context. EER {value_pct}.",
            "Feature distances carry meaning. EER {value_pct}. The model reads identity.",
        ],
        "mastering": [
            "Strong identity separation. EER {value_pct} at epoch {epoch} — near publication-ready performance.",
            "The model handles pose, illumination, and ageing variation. EER {value_pct}.",
            "Epoch {epoch}: robust verification under challenging conditions. EER {value_pct}.",
            "Impostor rejection is reliable. EER {value_pct}, delta {delta}.",
        ],
        "polishing": [
            "Final calibration at EER {value_pct}. Epoch {epoch} — the identity model is ready for the field.",
            "Last decimal points of separation. EER {value_pct}. The model operates near theoretical limits.",
            "Epoch {epoch}: threshold calibrated, confidence high. EER {value_pct}.",
            "Exceptional identity verification. EER {value_pct} at epoch {epoch}.",
        ],
    },
    # ── GAZE ──────────────────────────────────────────────────────────────────
    "gaze": {
        "awakening": [
            "The gaze model is lost. MAE {value}° at epoch {epoch} — predictions scatter across the visual field.",
            "Epoch {epoch}: gaze vectors point nowhere useful. MAE {value}°. The eye has not yet learned to follow.",
            "Random fixations define the beginning. MAE {value}° at epoch {epoch}.",
            "The model sees the face but not the gaze. MAE {value}°. The signal is there, hidden in the features.",
        ],
        "learning": [
            "Gaze direction emerges. MAE {value}° at epoch {epoch} — the model follows coarse head orientation.",
            "Rough vectors form. MAE {value}°, delta {delta}. The model learns left from right.",
            "Epoch {epoch}: horizontal gaze is captured first. MAE {value}°.",
            "The eye model finds its footing. MAE {value}° and falling toward clinical accuracy.",
        ],
        "understanding": [
            "Gaze estimation improves to MAE {value}° at epoch {epoch}. Fine angular features emerge.",
            "The model reads subtle iris cues. MAE {value}°. Human-level understanding approaches.",
            "Epoch {epoch}: vertical and horizontal gaze both captured well. MAE {value}°.",
            "Reliable gaze tracking in natural conditions. MAE {value}°.",
        ],
        "mastering": [
            "Accurate fixation prediction. MAE {value}° at epoch {epoch} — the model tracks gaze under mild variation.",
            "Sub-degree improvements per step. MAE {value}°, delta {delta}.",
            "Epoch {epoch}: the model handles glasses, makeup, and partial occlusion. MAE {value}°.",
            "Near-calibration accuracy. MAE {value}°. Strong performance without a calibration step.",
        ],
        "polishing": [
            "Clinical precision at MAE {value}°. Epoch {epoch} — ready for gaze-contingent applications.",
            "The last half-degree is won by careful attention. MAE {value}°.",
            "Epoch {epoch}: robust across head poses and distances. MAE {value}°.",
            "Exceptional gaze estimation. MAE {value}° at epoch {epoch}.",
        ],
    },
    # ── NLP ───────────────────────────────────────────────────────────────────
    "nlp": {
        "awakening": [
            "The language model is confused by everything. Perplexity {value} at epoch {epoch} — every token is a surprise.",
            "Epoch {epoch}: the model assigns nearly equal probability to all tokens. Perplexity {value}.",
            "Language is noise. Perplexity {value} at epoch {epoch}. The model has not yet found the signal.",
            "Random guesses define epoch {epoch}. Perplexity {value}. The gradient will carve order from chaos.",
        ],
        "learning": [
            "Common words become predictable. Perplexity falls to {value} at epoch {epoch}.",
            "The model learns function words first. Perplexity {value}, delta {delta}.",
            "Epoch {epoch}: n-gram patterns crystallise. Perplexity {value} and falling.",
            "The vocabulary narrows toward context. Perplexity {value}. The model finds language rhythm.",
        ],
        "understanding": [
            "Semantic relationships emerge. Perplexity {value} at epoch {epoch} — the model grasps grammar.",
            "Long-range dependencies form. Perplexity {value}. The model reads meaning, not just form.",
            "Epoch {epoch}: topic coherence improves. Perplexity {value}.",
            "The model builds a world model in miniature. Perplexity {value}, delta {delta}.",
        ],
        "mastering": [
            "Fluent predictions at perplexity {value}. Epoch {epoch} — the model generates coherent text.",
            "Rare words become tractable. Perplexity {value}. The model handles the long tail.",
            "Epoch {epoch}: discourse structure is captured. Perplexity {value}.",
            "Near-human fluency approaches. Perplexity {value}, delta {delta}.",
        ],
        "polishing": [
            "Final refinements. Perplexity {value} at epoch {epoch} — the language model approaches its limit.",
            "Each epoch squeezes perplexity lower. {value}. Excellence within reach.",
            "Epoch {epoch}: calibrated, coherent, ready. Perplexity {value}.",
            "The model speaks clearly. Perplexity {value} at epoch {epoch}.",
        ],
    },
    # ── GENERATIVE ────────────────────────────────────────────────────────────
    "generative": {
        "awakening": [
            "The generator produces noise. FID {value} at epoch {epoch} — output and reality share nothing yet.",
            "Epoch {epoch}: samples are blobs of colour. FID {value}. The discriminator wins every round.",
            "Random textures emerge from the latent space. FID {value}. The model has not yet learned to imagine.",
            "Epoch {epoch}: the generator guesses the distribution. FID {value}. The journey begins.",
        ],
        "learning": [
            "Rough structure appears. FID {value} at epoch {epoch} — the model finds coarse domain features.",
            "The generator beats the random baseline. FID {value}, delta {delta}.",
            "Epoch {epoch}: blobs resolve into shapes. FID {value}.",
            "Frequency statistics align with the real distribution. FID {value} and falling.",
        ],
        "understanding": [
            "Domain-specific features emerge. FID {value} at epoch {epoch} — outputs are recognisably on-task.",
            "The generator captures object-level structure. FID {value}.",
            "Epoch {epoch}: samples pass a casual inspection. FID {value}.",
            "The model has learned what things look like. FID {value}, delta {delta}.",
        ],
        "mastering": [
            "Realistic outputs at FID {value}. Epoch {epoch} — generation is compelling.",
            "Fine textures and coherent structure. FID {value}. The model has mastered the domain.",
            "Epoch {epoch}: samples fool most observers. FID {value}.",
            "Near-photorealistic quality approaches. FID {value}, delta {delta}.",
        ],
        "polishing": [
            "Final touches. FID {value} at epoch {epoch} — the generator refines its masterwork.",
            "Each sample is a plausible specimen of the domain. FID {value}.",
            "Epoch {epoch}: diversity and fidelity balanced. FID {value}.",
            "The model creates. FID {value} at epoch {epoch} — indistinguishable from real.",
        ],
    },
}

# ── Farsi (fa) — classification only (demonstrative; other tasks follow same pattern)
FA_CLASSIFICATION: dict[str, list[str]] = {
    "awakening": [
        "مدل در دوره {epoch} بیدار می‌شود. دقت {value_pct} — سفر هزار دوره با یک گرادیان آغاز می‌شود.",
        "اولین الگوها از میان نویز نمایان می‌شوند. دقت {value_pct}. مدل در حال یادگیری دیدن است.",
    ],
    "learning": [
        "گرادیان‌ها جاری می‌شوند. دقت به {value_pct} می‌رسد در دوره {epoch}.",
        "مدل ساختار داده‌ها را کشف می‌کند. دقت {value_pct}. دلتا: {delta}.",
    ],
    "understanding": [
        "بازنمایی‌های عمیق شکل می‌گیرند. دقت {value_pct} در دوره {epoch}.",
        "مدل فراتر از حفظ کردن رفته است. دقت {value_pct}.",
    ],
    "mastering": [
        "عملکرد نزدیک به کارشناس در {value_pct}. دوره {epoch}.",
        "مدل وظیفه را درونی کرده است. دقت {value_pct}.",
    ],
    "polishing": [
        "صیقل‌کاری تا {value_pct}. اصلاحات نهایی مدل را به اوج می‌رساند. دوره {epoch}.",
        "درخشش حاصل شد. دقت {value_pct} — مدل آماده دنیاست.",
    ],
}

# ── French (fr) — classification only (demonstrative)
FR_CLASSIFICATION: dict[str, list[str]] = {
    "awakening": [
        "Le modèle s'éveille à l'époque {epoch}. Précision : {value_pct} — le voyage commence.",
        "Les premiers motifs émergent du bruit. Précision {value_pct}. Le modèle apprend à voir.",
    ],
    "learning": [
        "Les gradients coulent, les représentations s'affinent. Précision {value_pct} à l'époque {epoch}.",
        "Le modèle découvre la structure de ses données. Précision {value_pct}, delta {delta}.",
    ],
    "understanding": [
        "Des représentations profondes se forment. Précision {value_pct} — le modèle saisit la structure.",
        "La généralisation s'améliore. Précision {value_pct} à l'époque {epoch}.",
    ],
    "mastering": [
        "Performance proche de l'expert à {value_pct}. Époque {epoch}.",
        "Le modèle a intériorisé la tâche. Précision {value_pct}.",
    ],
    "polishing": [
        "Peaufinage à {value_pct}. Les derniers réglages portent le modèle à son sommet. Époque {epoch}.",
        "Excellence atteinte. Précision {value_pct} — un modèle prêt pour le monde.",
    ],
}


def main() -> None:
    created = 0
    for task, phases in TEMPLATES.items():
        for phase, lines in phases.items():
            path = BASE / task / f"{phase}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            created += 1

    # i18n — classification fa
    for phase, lines in FA_CLASSIFICATION.items():
        path = BASE / "classification" / f"{phase}.fa.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        created += 1

    # i18n — classification fr
    for phase, lines in FR_CLASSIFICATION.items():
        path = BASE / "classification" / f"{phase}.fr.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        created += 1

    print(f"Created {created} template files under {BASE}")


if __name__ == "__main__":
    main()
