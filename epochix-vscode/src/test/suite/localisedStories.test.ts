/**
 * The extension tells its stories in the configured language.
 *
 * Its narrator carried an English-only copy of the templates, so a Farsi or
 * French user got English stories from the standalone engine whatever
 * `epochix.locale` said — and, through the sidecar, English too, because the
 * locale was never sent when a run was created there. The templates are now
 * generated from the Python engine's, in every locale it has.
 *
 * Driven through the real StandaloneEngine. Variants are chosen per run id, so
 * the assertions hold for any variant.
 */
import * as assert from "assert";

import { StandaloneEngine } from "../../webview/StandaloneEngine";
import { displayMetric, _VARIANTS } from "../../story/narrator";
import {
  LOCALES,
  PHASE_TEMPLATES,
  SPECIAL_TEMPLATES,
} from "../../story/narratives.generated";
import type { StoryFrameMsg } from "../../webview/messages";

const PERSIAN = /[\u0600-\u06FF]/;

const SHAPES: Record<string, string[]> = {
  accuracy: Array.from({ length: 8 }, (_, i) =>
    `Epoch ${i + 1}/8 - loss: ${(1.2 - i * 0.1).toFixed(4)} - val_loss: ${(1.3 - i * 0.1).toFixed(4)}` +
    ` - val_accuracy: ${(0.5 + i * 0.05).toFixed(4)}`),
  loss: Array.from({ length: 8 }, (_, i) =>
    `Epoch ${i + 1}/8 - loss: ${(1.2 - i * 0.1).toFixed(4)} - val_loss: ${(1.3 - i * 0.12).toFixed(4)}`),
  pastPeak: [0.7, 0.8, 0.85, 0.83, 0.78, 0.74, 0.7, 0.66].map((v, i) =>
    `Epoch ${i + 1}/8 - loss: 0.5 - val_accuracy: ${v.toFixed(4)}`),
  diverged: [
    "Epoch 1/6 - loss: 0.9000 - val_loss: 0.9500",
    "Epoch 2/6 - loss: 0.7000 - val_loss: 0.7600",
    "Epoch 3/6 - loss: 0.5000 - val_loss: 0.5900",
    "Epoch 4/6 - loss: nan - val_loss: nan",
    "Epoch 5/6 - loss: nan - val_loss: nan",
  ],
};

/** Whether `text` is one of `locale`'s templates with its placeholders filled. */
function isFilledFrom(text: string, locale: (typeof LOCALES)[number]): boolean {
  const all = [
    ...Object.values(PHASE_TEMPLATES[locale]).flat(),
    ...Object.values(SPECIAL_TEMPLATES[locale]).flat(),
  ];
  return all.some((t) => {
    let at = 0;
    for (const piece of t.split(/\{[a-z_]+\}/)) {
      if (!piece) continue;
      const found = text.indexOf(piece, at);
      if (found < 0) return false;
      at = found + piece.length;
    }
    return true;
  });
}

function frames(lines: string[], locale: string): StoryFrameMsg[] {
  const engine = new StandaloneEngine(undefined, locale);
  const out: StoryFrameMsg[] = [];
  for (const line of lines) out.push(...engine.feed(line + "\n"));
  out.push(...engine.flush());
  assert.ok(out.length > 0, `no story at all (${locale})`);
  return out;
}

suite("Stories are told in the configured language", () => {
  for (const [shape, lines] of Object.entries(SHAPES)) {
    test(`${shape}: Farsi is Farsi`, () => {
      for (const f of frames(lines, "fa")) {
        assert.ok(PERSIAN.test(f.narrative), `English story under fa: ${f.narrative}`);
      }
    });

    test(`${shape}: French is not the English story`, () => {
      const en = frames(lines, "en").map((f) => f.narrative);
      const fr = frames(lines, "fr").map((f) => f.narrative);
      assert.strictEqual(fr.length, en.length);
      fr.forEach((n, i) => assert.notStrictEqual(n, en[i], `untranslated under fr: ${n}`));
    });

    for (const locale of LOCALES) {
      test(`${shape}: no placeholder is left unfilled (${locale})`, () => {
        for (const f of frames(lines, locale)) {
          assert.ok(!/\{[a-z_]+\}/.test(f.narrative), `unfilled placeholder: ${f.narrative}`);
        }
      });
    }
  }

  test("an unknown locale falls back to English rather than failing", () => {
    for (const f of frames(SHAPES.loss, "xx")) {
      assert.ok(isFilledFrom(f.narrative, "en"), `not an English story: ${f.narrative}`);
    }
  });

  for (const locale of LOCALES) {
    test(`every story is a filled ${locale} template`, () => {
      for (const lines of Object.values(SHAPES)) {
        for (const f of frames(lines, locale)) {
          assert.ok(isFilledFrom(f.narrative, locale), `not from the ${locale} set: ${f.narrative}`);
        }
      }
    });
  }

  test("the split word follows the sentence's language and word order", () => {
    assert.strictEqual(displayMetric("val_MAE", "en"), "validation MAE");
    assert.strictEqual(displayMetric("val_MAE", "fr"), "MAE de validation");
    assert.ok(PERSIAN.test(displayMetric("val_MAE", "fa")));
    assert.ok(!/validation/.test(displayMetric("val_loss", "fa")));
  });

  test("every locale has every template set, and every variant keeps its numbers", () => {
    const keys = Object.keys(PHASE_TEMPLATES.en);
    assert.ok(keys.length >= 40, `only ${keys.length} phase template sets`);
    for (const locale of LOCALES) {
      assert.deepStrictEqual(Object.keys(PHASE_TEMPLATES[locale]).sort(), [...keys].sort());
      for (const k of keys) assert.ok(PHASE_TEMPLATES[locale][k].length > 0, `${locale} ${k}`);
      for (const v of SPECIAL_TEMPLATES[locale].diverged) assert.ok(v.includes("{value}"), v);
      for (const v of SPECIAL_TEMPLATES[locale].pastPeak) assert.ok(v.includes("{best}"), v);
    }
    assert.ok(_VARIANTS.SINGLE_READING.length >= LOCALES.length);
  });
});

suite("A single result is reported as a result", () => {
  test("one reading with no epoch is not narrated as the start of training", () => {
    for (const locale of LOCALES) {
      const f = frames(["Test accuracy: 0.9123"], locale);
      const text = f[f.length - 1].narrative;
      const filled = SPECIAL_TEMPLATES[locale].singleReading.some((t) => {
        const [head] = t.split("{");
        return text.startsWith(head);
      });
      assert.ok(filled, `not a single-reading story (${locale}): ${text}`);
      assert.ok(text.includes("0.9123"), text);
    }
  });
});

suite("Warnings and milestones are told in the configured language", () => {
  // Val loss rising while train loss falls: an overfitting warning, plus grade
  // and phase milestones along the way.
  const overfit = [
    [1.0, 1.1, 0.3], [0.8, 1.2, 0.55], [0.6, 1.3, 0.7], [0.4, 1.4, 0.8], [0.3, 1.5, 0.86],
  ].map(([t, v, a], i) =>
    `Epoch ${i + 1}/5 - loss: ${t.toFixed(4)} - val_loss: ${v.toFixed(4)} - val_accuracy: ${a.toFixed(4)}`);

  function messages(locale: string): { kinds: string[]; texts: string[] } {
    const engine = new StandaloneEngine(undefined, locale);
    for (const line of overfit) engine.feed(line + "\n");
    engine.flush();
    const all = [...engine.milestones(), ...engine.warnings()];
    return { kinds: all.map((m) => m.kind), texts: all.map((m) => m.message) };
  }

  test("the run produces the messages under test", () => {
    const { kinds } = messages("en");
    assert.ok(kinds.includes("overfit"), JSON.stringify(kinds));
    assert.ok(kinds.includes("first_metric"), JSON.stringify(kinds));
  });

  for (const locale of ["fa", "fr"]) {
    test(`every message is translated (${locale})`, () => {
      const en = messages("en");
      const other = messages(locale);
      assert.deepStrictEqual(other.kinds, en.kinds);
      other.texts.forEach((t, i) => {
        assert.notStrictEqual(t, en.texts[i], `untranslated under ${locale}: ${t}`);
        assert.ok(!/\{[a-z_]+\}/.test(t), `unfilled placeholder: ${t}`);
        if (locale === "fa") assert.ok(PERSIAN.test(t), `English under fa: ${t}`);
      });
    });
  }
});
