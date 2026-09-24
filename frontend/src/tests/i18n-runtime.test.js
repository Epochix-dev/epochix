/**
 * Runtime localisation: text the panels write themselves.
 *
 * fa.json and fr.json held translations for the epoch label, the phase names,
 * the connection dot, task names and more — and no code read them, so those
 * stayed English in every locale. Forty of sixty keys were dead. The reverse
 * gap existed too: the extension's engine emits milestone kinds no dictionary
 * had a title for, so its timeline cards were headed "grade_transition".
 *
 * These pin both directions, against the real sources.
 */
import { describe, it, expect, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { setActiveI18n, t, resolveKey } from '../i18n/apply.js';
import en from '../i18n/en.json';
import fa from '../i18n/fa.json';
import fr from '../i18n/fr.json';
import { EpochScrubber } from '../visualizations/EpochScrubber.js';
import { PhaseJourney } from '../visualizations/PhaseJourney.js';
import { TimelineStory } from '../visualizations/TimelineStory.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, '..');
const REPO = path.resolve(SRC, '..', '..');
const LOCALES = { en, fa, fr };

function sources(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === 'tests' ? [] : sources(p);
    return e.name.endsWith('.js') ? [p] : [];
  });
}
const CODE = sources(SRC).map((f) => fs.readFileSync(f, 'utf8')).join('\n')
  + fs.readFileSync(path.join(SRC, '..', 'index.html'), 'utf8');

function leaves(obj, prefix = '') {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? leaves(v, `${prefix}${k}.`) : [`${prefix}${k}`]);
}

// Groups read with a computed key: t(`phases.${phase}`), i18n.milestones[kind].
const DYNAMIC_GROUPS = ['phases', 'tasks', 'milestones'];

afterEach(() => setActiveI18n(null));

describe('dictionaries', () => {
  it('every locale has exactly the English keys', () => {
    const keys = leaves(en).sort();
    for (const [name, dict] of Object.entries(LOCALES)) {
      expect(leaves(dict).sort(), name).toEqual(keys);
    }
  });

  it('every static key the code asks for exists', () => {
    const asked = [
      ...CODE.matchAll(/\bt\(\s*'([\w.]+)'/g),
      ...CODE.matchAll(/data-i18n(?:-title)?="([\w.]+)"/g),
    ].map((m) => m[1]).filter((k) => k !== 'dotted.key');
    expect(asked.length).toBeGreaterThan(10);
    for (const k of asked) expect(resolveKey(en, k), k).toBeTypeOf('string');
  });

  it('no key is dead', () => {
    const dead = leaves(en).filter((k) =>
      !DYNAMIC_GROUPS.includes(k.split('.')[0]) && !CODE.includes(`'${k}'`) && !CODE.includes(`"${k}"`));
    expect(dead).toEqual([]);
  });
});

describe('milestone titles', () => {
  // Every kind either engine can emit, read from the engines themselves.
  const py = fs.readFileSync(path.join(REPO, 'src/epochix/story_engine/milestones.py'), 'utf8')
    + fs.readFileSync(path.join(REPO, 'src/epochix/story_engine/__init__.py'), 'utf8');
  const ts = fs.readFileSync(path.join(REPO, 'epochix-vscode/src/webview/StandaloneEngine.ts'), 'utf8');
  const kinds = new Set([
    ...[...py.matchAll(/kind="(\w+)"/g)].map((m) => m[1]),
    ...[25, 50, 75, 90].map((n) => `first_above_${n}`), // built with an f-string
    ...[...ts.matchAll(/kind: "(\w+)"/g)].map((m) => m[1]),
  ]);

  it('finds the kinds it is checking', () => {
    for (const k of ['best_so_far', 'biggest_jump', 'training_complete', 'grade_transition', 'first_metric']) {
      expect(kinds.has(k), k).toBe(true);
    }
  });

  for (const [name, dict] of Object.entries(LOCALES)) {
    it(`${name} titles every kind`, () => {
      const missing = [...kinds].filter((k) => typeof dict.milestones[k] !== 'string');
      expect(missing).toEqual([]);
    });
  }

  it('a card is titled from the dictionary, not with the raw kind', () => {
    const el = document.createElement('div');
    const tl = new TimelineStory(el, fr.milestones);
    tl._onState({ milestones: [{ kind: 'grade_transition', epoch: 3, message: 'x' }], live: true, run: null });
    expect(el.querySelector('.tc-title').textContent).toBe(fr.milestones.grade_transition);
  });
});

describe('panels speak the active locale', () => {
  it('t() falls back to the English it was given when no dictionary is set', () => {
    expect(t('labels.epoch', 'Epoch')).toBe('Epoch');
  });

  for (const [name, dict] of Object.entries(LOCALES)) {
    it(`epoch label in ${name}`, () => {
      setActiveI18n(dict);
      const el = document.createElement('div');
      const scrubber = new EpochScrubber(el);
      scrubber._updateLabel({ currentFrame: { epoch: 4 } });
      expect(scrubber._label.textContent).toBe(`${dict.labels.epoch} 4`);
    });

    it(`phase journey in ${name}`, () => {
      setActiveI18n(dict);
      const el = document.createElement('div');
      const pj = new PhaseJourney(el);
      const frames = [
        { epoch: 1, phase: 'awakening', grade: 'D' },
        { epoch: 2, phase: 'learning', grade: 'C' },
      ];
      pj._render({ frames, currentFrame: frames[1] });
      const names = [...el.querySelectorAll('.pj-seg-name')].map((n) => n.textContent);
      expect(names).toEqual([dict.phases.awakening, dict.phases.learning]);
    });
  }

  it('phase names carry no emoji of their own (the panels draw the icon)', () => {
    for (const dict of Object.values(LOCALES)) {
      for (const v of Object.values(dict.phases)) expect(v).toMatch(/^[\p{L} ]+$/u);
    }
  });
});
