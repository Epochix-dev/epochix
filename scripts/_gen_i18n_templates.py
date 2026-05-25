"""Generate i18n (fa + fr) narrative template files for remaining task types.

Run with:  python scripts/_gen_i18n_templates.py
"""
from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parents[1] / "src/model_story/story_engine/templates"

# ---------------------------------------------------------------------------
# Template content: task → phase → locale → [variant, ...]
# Each variant = one line in the output file.
# Placeholders: {epoch}, {value}, {value_pct}, {delta}
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, dict[str, list[str]]]] = {
    # ── Detection ─────────────────────────────────────────────────────────
    "detection": {
        "awakening": {
            "fa": [
                "مدل در دوره {epoch} اولین اشیاء را تشخیص می‌دهد. mAP50: {value_pct} — بینایی ماشین بیدار می‌شود.",
                "اولین کادرهای تشخیص از نویز ظاهر می‌شوند. mAP50 {value_pct}. مدل در حال یادگیری دیدن اشیاء است.",
            ],
            "fr": [
                "Le modèle détecte ses premiers objets à l'époque {epoch}. mAP50 : {value_pct} — la vision artificielle s'éveille.",
                "Les premières boîtes de détection émergent du bruit. mAP50 {value_pct}. Le modèle apprend à voir les objets.",
            ],
        },
        "learning": {
            "fa": [
                "mAP50 به {value_pct} رسید. مدل در دوره {epoch} در حال یادگیری الگوهای بصری است.",
                "دقت تشخیص بهبود می‌یابد — mAP50 {value_pct}. مدل در حال درک تناسب‌های تصویری است.",
                "مدل در دوره {epoch} با mAP50 {value_pct} اشیاء را با اطمینان بیشتری شناسایی می‌کند.",
            ],
            "fr": [
                "mAP50 atteint {value_pct}. À l'époque {epoch}, le modèle apprend les motifs visuels.",
                "La précision de détection s'améliore — mAP50 {value_pct}. Le modèle comprend les proportions.",
                "À l'époque {epoch}, mAP50 {value_pct} — les objets sont identifiés avec plus de confiance.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، mAP50 = {value_pct}. مدل زمینه تصویری را درک می‌کند.",
                "mAP50 {value_pct} — مدل ویژگی‌های پیچیده تشخیص را می‌فهمد. درک عمیق‌تر می‌شود.",
            ],
            "fr": [
                "À l'époque {epoch}, mAP50 = {value_pct}. Le modèle saisit le contexte visuel.",
                "mAP50 {value_pct} — le modèle comprend les caractéristiques complexes de détection.",
            ],
        },
        "mastering": {
            "fa": [
                "مدل در دوره {epoch} در تشخیص تسلط پیدا می‌کند. mAP50 {value_pct} — دقت چشمگیر است.",
                "mAP50 = {value_pct}. الگوریتم تشخیص به اوج کارایی می‌رسد.",
                "در دوره {epoch}، مدل با mAP50 {value_pct} به سطح متخصص می‌رسد.",
            ],
            "fr": [
                "Le modèle maîtrise la détection à l'époque {epoch}. mAP50 {value_pct} — précision remarquable.",
                "mAP50 = {value_pct}. L'algorithme de détection atteint son efficacité maximale.",
                "À l'époque {epoch}, mAP50 {value_pct} — niveau expert atteint.",
            ],
        },
        "polishing": {
            "fa": [
                "صیقل‌کاری نهایی. mAP50 {value_pct} — مدل تشخیص به اوج خود رسیده.",
                "دوره {epoch}: mAP50 {value_pct}. هر بهینه‌سازی اندک دقت تشخیص را بهتر می‌کند.",
            ],
            "fr": [
                "Polissage final. mAP50 {value_pct} — le modèle de détection atteint son apogée.",
                "Époque {epoch} : mAP50 {value_pct}. Chaque ajustement affine la précision de détection.",
            ],
        },
    },

    # ── Regression ────────────────────────────────────────────────────────
    "regression": {
        "awakening": {
            "fa": [
                "مدل در دوره {epoch} اولین پیش‌بینی‌ها را انجام می‌دهد. MAE: {value} — خطا در حال کاهش است.",
                "رگرسیون آغاز می‌شود. MAE = {value} در دوره {epoch}. مدل در حال یادگیری روابط داده است.",
            ],
            "fr": [
                "Le modèle fait ses premières prédictions à l'époque {epoch}. MAE : {value} — l'erreur commence à baisser.",
                "La régression s'éveille. MAE = {value} à l'époque {epoch}. Le modèle apprend les relations entre données.",
            ],
        },
        "learning": {
            "fa": [
                "خطای MAE به {value} کاهش یافت. مدل در دوره {epoch} روابط پنهان را می‌آموزد.",
                "MAE = {value} — خطا در حال افت است. مدل الگوهای غیرخطی را کشف می‌کند.",
                "در دوره {epoch}، MAE {value}. بهبود پیوسته در دقت پیش‌بینی.",
            ],
            "fr": [
                "L'erreur MAE descend à {value}. À l'époque {epoch}, le modèle apprend les relations cachées.",
                "MAE = {value} — l'erreur est en baisse. Le modèle découvre les motifs non-linéaires.",
                "À l'époque {epoch}, MAE {value}. Amélioration continue de la précision des prédictions.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، MAE = {value}. مدل الگوهای پیچیده را درک می‌کند.",
                "MAE {value} — پیش‌بینی‌ها دقیق‌تر می‌شوند. مدل روابط عمیق‌تری می‌بیند.",
            ],
            "fr": [
                "À l'époque {epoch}, MAE = {value}. Le modèle saisit les motifs complexes.",
                "MAE {value} — les prédictions se précisent. Le modèle voit des relations plus profondes.",
            ],
        },
        "mastering": {
            "fa": [
                "MAE = {value} — مدل در تخمین دقیق استاد می‌شود. پیش‌بینی‌ها بسیار دقیق‌اند.",
                "در دوره {epoch}، MAE به {value} رسید. مهارت رگرسیون به اوج می‌رسد.",
            ],
            "fr": [
                "MAE = {value} — le modèle maîtrise l'estimation précise. Prédictions très exactes.",
                "À l'époque {epoch}, MAE atteint {value}. La compétence en régression culmine.",
            ],
        },
        "polishing": {
            "fa": [
                "بهینه‌سازی نهایی. MAE = {value} — مدل به دقت بالا رسیده.",
                "دوره {epoch}: MAE {value}. هر اپوک بهبودی اندک اما معنادار می‌آورد.",
            ],
            "fr": [
                "Optimisation finale. MAE = {value} — le modèle atteint une haute précision.",
                "Époque {epoch} : MAE {value}. Chaque epoch apporte une amélioration minime mais significative.",
            ],
        },
    },

    # ── Biometric ─────────────────────────────────────────────────────────
    "biometric": {
        "awakening": {
            "fa": [
                "مدل در دوره {epoch} اولین نمونه‌های بیومتریک را پردازش می‌کند. EER: {value_pct} — شناسایی آغاز می‌شود.",
                "اثرانگشت دیجیتال در حال شکل‌گیری است. EER = {value_pct} در دوره {epoch}. مدل در حال یادگیری تأیید هویت است.",
            ],
            "fr": [
                "Le modèle traite ses premiers échantillons biométriques à l'époque {epoch}. EER : {value_pct} — l'identification commence.",
                "L'empreinte numérique prend forme. EER = {value_pct} à l'époque {epoch}. Le modèle apprend à vérifier l'identité.",
            ],
        },
        "learning": {
            "fa": [
                "EER به {value_pct} کاهش یافت. مدل ویژگی‌های بیومتریک متمایز را می‌آموزد.",
                "در دوره {epoch}، EER = {value_pct}. مدل مرزهای تصمیم‌گیری را بهتر می‌شناسد.",
                "EER {value_pct} — نرخ خطا در حال کاهش است. تأیید هویت دقیق‌تر می‌شود.",
            ],
            "fr": [
                "EER descend à {value_pct}. Le modèle apprend les traits biométriques distinctifs.",
                "À l'époque {epoch}, EER = {value_pct}. Le modèle mieux cerne les frontières de décision.",
                "EER {value_pct} — le taux d'erreur baisse. La vérification d'identité gagne en précision.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، EER = {value_pct}. مدل تفاوت‌های ظریف بیومتریک را درک می‌کند.",
                "EER {value_pct} — مدل ویژگی‌های هویتی پیچیده را می‌فهمد. اطمینان بالاتر است.",
            ],
            "fr": [
                "À l'époque {epoch}, EER = {value_pct}. Le modèle discerne les subtilités biométriques.",
                "EER {value_pct} — le modèle comprend les caractéristiques identitaires complexes.",
            ],
        },
        "mastering": {
            "fa": [
                "EER = {value_pct} — مدل در تأیید هویت تسلط پیدا می‌کند. نتایج بسیار دقیق.",
                "در دوره {epoch}، EER {value_pct}. سیستم بیومتریک به دقت بالا می‌رسد.",
            ],
            "fr": [
                "EER = {value_pct} — le modèle maîtrise la vérification biométrique. Résultats très précis.",
                "À l'époque {epoch}, EER {value_pct}. Le système biométrique atteint une haute précision.",
            ],
        },
        "polishing": {
            "fa": [
                "صیقل نهایی. EER = {value_pct} — سطح بالایی از تأیید هویت حاصل شده.",
                "دوره {epoch}: EER {value_pct}. بهینه‌سازی‌های اندک اما مهم در دقت شناسایی.",
            ],
            "fr": [
                "Polissage final. EER = {value_pct} — haute précision d'identification atteinte.",
                "Époque {epoch} : EER {value_pct}. Optimisations mineures mais importantes en précision biométrique.",
            ],
        },
    },

    # ── Gaze ──────────────────────────────────────────────────────────────
    "gaze": {
        "awakening": {
            "fa": [
                "مدل در دوره {epoch} اولین بردارهای نگاه را تخمین می‌زند. MAE: {value}° — ردیابی چشم آغاز می‌شود.",
                "اولین پیش‌بینی‌های جهت نگاه. MAE = {value}° در دوره {epoch}. مدل در حال درک چشم انسان است.",
            ],
            "fr": [
                "Le modèle estime ses premiers vecteurs du regard à l'époque {epoch}. MAE : {value}° — le suivi oculaire commence.",
                "Premières prédictions de direction du regard. MAE = {value}° à l'époque {epoch}. Le modèle apprend à comprendre le regard humain.",
            ],
        },
        "learning": {
            "fa": [
                "خطای نگاه به {value}° کاهش یافت. مدل در دوره {epoch} جهت‌گیری چشم را می‌آموزد.",
                "MAE نگاه = {value}° — ردیابی دقیق‌تر می‌شود. مدل زوایای ظریف را یاد می‌گیرد.",
                "در دوره {epoch}، MAE چشم {value}°. پیش‌بینی جهت نگاه بهبود می‌یابد.",
            ],
            "fr": [
                "L'erreur de regard descend à {value}°. À l'époque {epoch}, le modèle apprend l'orientation oculaire.",
                "MAE regard = {value}° — le suivi se précise. Le modèle apprend les angles subtils.",
                "À l'époque {epoch}, MAE oculaire {value}°. La prédiction de direction du regard s'améliore.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، MAE نگاه = {value}°. مدل زمینه دیداری و جهت چشم را می‌فهمد.",
                "MAE {value}° — ردیابی نگاه به درک عمیق‌تری می‌رسد. مدل الگوهای پیچیده چشمی را می‌بیند.",
            ],
            "fr": [
                "À l'époque {epoch}, MAE regard = {value}°. Le modèle comprend le contexte visuel et la direction oculaire.",
                "MAE {value}° — le suivi du regard atteint une compréhension plus profonde.",
            ],
        },
        "mastering": {
            "fa": [
                "MAE نگاه {value}° — مدل در ردیابی دید تسلط پیدا می‌کند. دقت بسیار بالاست.",
                "در دوره {epoch}، MAE = {value}°. سیستم ردیابی چشم به اوج کارایی می‌رسد.",
            ],
            "fr": [
                "MAE regard {value}° — le modèle maîtrise le suivi oculaire. Précision très élevée.",
                "À l'époque {epoch}, MAE = {value}°. Le système de suivi du regard atteint son efficacité maximale.",
            ],
        },
        "polishing": {
            "fa": [
                "صیقل نهایی. MAE = {value}° — ردیابی نگاه به دقت بسیار بالا رسیده.",
                "دوره {epoch}: MAE نگاه {value}°. هر اپوک دقت ردیابی چشم را کمی بهتر می‌کند.",
            ],
            "fr": [
                "Polissage final. MAE = {value}° — suivi du regard très précis atteint.",
                "Époque {epoch} : MAE regard {value}°. Chaque epoch affine légèrement la précision du suivi oculaire.",
            ],
        },
    },

    # ── NLP ───────────────────────────────────────────────────────────────
    "nlp": {
        "awakening": {
            "fa": [
                "مدل زبانی در دوره {epoch} اولین توکن‌ها را پردازش می‌کند. پرپلکسیتی: {value} — زبان در حال کشف است.",
                "کلمات اول از میان نویز آماری نمایان می‌شوند. پرپلکسیتی = {value} در دوره {epoch}.",
            ],
            "fr": [
                "Le modèle linguistique traite ses premiers tokens à l'époque {epoch}. Perplexité : {value} — le langage est en cours d'exploration.",
                "Les premiers mots émergent du bruit statistique. Perplexité = {value} à l'époque {epoch}.",
            ],
        },
        "learning": {
            "fa": [
                "پرپلکسیتی به {value} کاهش یافت. مدل در دوره {epoch} ساختارهای زبانی را می‌آموزد.",
                "پرپلکسیتی = {value} — درک زبانی در حال رشد است. مدل الگوهای گرامری را کشف می‌کند.",
                "در دوره {epoch}، پرپلکسیتی {value}. مدل روابط معنایی را بهتر درک می‌کند.",
            ],
            "fr": [
                "La perplexité descend à {value}. À l'époque {epoch}, le modèle apprend les structures linguistiques.",
                "Perplexité = {value} — la compréhension linguistique croît. Le modèle découvre les motifs grammaticaux.",
                "À l'époque {epoch}, perplexité {value}. Le modèle comprend mieux les relations sémantiques.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، پرپلکسیتی = {value}. مدل معنا و زمینه را درک می‌کند.",
                "پرپلکسیتی {value} — مدل زبانی به درک عمیق‌تر می‌رسد. ابهام در حال کاهش است.",
            ],
            "fr": [
                "À l'époque {epoch}, perplexité = {value}. Le modèle comprend le sens et le contexte.",
                "Perplexité {value} — le modèle linguistique atteint une compréhension plus profonde.",
            ],
        },
        "mastering": {
            "fa": [
                "پرپلکسیتی {value} — مدل زبان را به خوبی مدل می‌کند. نتایج چشمگیر است.",
                "در دوره {epoch}، پرپلکسیتی = {value}. مدل زبانی به تسلط می‌رسد.",
            ],
            "fr": [
                "Perplexité {value} — le modèle maîtrise bien le langage. Résultats impressionnants.",
                "À l'époque {epoch}, perplexité = {value}. Le modèle linguistique atteint la maîtrise.",
            ],
        },
        "polishing": {
            "fa": [
                "صیقل نهایی. پرپلکسیتی = {value} — مدل زبانی به دقت بالا رسیده.",
                "دوره {epoch}: پرپلکسیتی {value}. هر بهینه‌سازی اندک کیفیت زبانی را بهتر می‌کند.",
            ],
            "fr": [
                "Polissage final. Perplexité = {value} — modèle linguistique très précis.",
                "Époque {epoch} : perplexité {value}. Chaque optimisation mineure améliore la qualité linguistique.",
            ],
        },
    },

    # ── Generative ────────────────────────────────────────────────────────
    "generative": {
        "awakening": {
            "fa": [
                "مدل مولد در دوره {epoch} اولین تصاویر را خلق می‌کند. FID: {value} — خلاقیت آغاز می‌شود.",
                "اولین نمونه‌های مولد از نویز ظاهر می‌شوند. FID = {value} در دوره {epoch}.",
            ],
            "fr": [
                "Le modèle génératif crée ses premières images à l'époque {epoch}. FID : {value} — la créativité commence.",
                "Les premiers échantillons génératifs émergent du bruit. FID = {value} à l'époque {epoch}.",
            ],
        },
        "learning": {
            "fa": [
                "FID به {value} کاهش یافت. کیفیت تصاویر مولد در دوره {epoch} در حال بهبود است.",
                "FID = {value} — تصاویر مولد واقعی‌تر می‌شوند. مدل توزیع را می‌آموزد.",
                "در دوره {epoch}، FID {value}. مدل مولد الگوهای بصری واقعی را یاد می‌گیرد.",
            ],
            "fr": [
                "FID descend à {value}. La qualité des images génératives s'améliore à l'époque {epoch}.",
                "FID = {value} — les images génératives deviennent plus réalistes. Le modèle apprend la distribution.",
                "À l'époque {epoch}, FID {value}. Le modèle génératif apprend les motifs visuels réels.",
            ],
        },
        "understanding": {
            "fa": [
                "در دوره {epoch}، FID = {value}. مدل توزیع داده‌های واقعی را درک می‌کند.",
                "FID {value} — تصاویر مولد به واقعیت نزدیک‌تر می‌شوند. مدل از کشف به فهم می‌رسد.",
            ],
            "fr": [
                "À l'époque {epoch}, FID = {value}. Le modèle comprend la distribution des données réelles.",
                "FID {value} — les images génératives se rapprochent de la réalité.",
            ],
        },
        "mastering": {
            "fa": [
                "FID = {value} — مدل مولد در حال تسلط است. تصاویر بسیار واقعی به نظر می‌رسند.",
                "در دوره {epoch}، FID {value}. مهارت مولد به اوج می‌رسد.",
            ],
            "fr": [
                "FID = {value} — le modèle génératif maîtrise sa tâche. Images très réalistes.",
                "À l'époque {epoch}, FID {value}. La compétence générative culmine.",
            ],
        },
        "polishing": {
            "fa": [
                "صیقل نهایی. FID = {value} — تصاویر مولد به کیفیت بسیار بالا رسیده‌اند.",
                "دوره {epoch}: FID {value}. هر اپوک کیفیت بصری را کمی بیشتر صیقل می‌دهد.",
            ],
            "fr": [
                "Polissage final. FID = {value} — images génératives de très haute qualité.",
                "Époque {epoch} : FID {value}. Chaque epoch affine légèrement la qualité visuelle.",
            ],
        },
    },
}

PHASES = ["awakening", "learning", "understanding", "mastering", "polishing"]


def main() -> None:
    written = 0
    for task, phases in TEMPLATES.items():
        task_dir = TEMPLATES_DIR / task
        task_dir.mkdir(parents=True, exist_ok=True)
        for phase in PHASES:
            for locale, variants in phases[phase].items():
                path = task_dir / f"{phase}.{locale}.txt"
                path.write_text("\n".join(variants) + "\n", encoding="utf-8")
                print(f"  wrote {path.relative_to(TEMPLATES_DIR)}")
                written += 1
    print(f"\nDone — {written} files written.")


if __name__ == "__main__":
    main()
