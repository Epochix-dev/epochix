/**
 * What a run counts by.
 *
 * A run with no epochs has its own counter in every frame's `epoch` field — a
 * boosting round, an iteration, a step — and the dashboard called each of
 * them an epoch: nanoGPT's chart ran to 2000 on an axis labelled "epoch", and
 * a CatBoost run's sixty rounds read "Over 60 epochs". The engine says what
 * the number counts on each frame (`counter`), and everything that names it
 * here asks this module.
 *
 * Null is a frame with nothing in its epoch field, or a run stored before the
 * counter was recorded: worded as an epoch, as every run used to be.
 */
import { t } from './i18n/apply.js';

const WORDS = {
  epoch: { one: 'epoch', many: 'epochs', short: 'ep', title: 'Epoch', readings: 'epochs' },
  step: { one: 'step', many: 'steps', short: 'step', title: 'Step', readings: 'readings' },
  iteration: {
    one: 'iteration', many: 'iterations', short: 'iter', title: 'Iteration', readings: 'readings',
  },
  round: { one: 'round', many: 'rounds', short: 'round', title: 'Round', readings: 'readings' },
};

export const COUNTERS = Object.keys(WORDS);

/**
 * The counter of a run, from its frames — the latest one that names it, as
 * `latestPrimaryKey` reads the story's metric (the run record does not hold
 * it).
 *
 * @param {object[]|null|undefined} frames
 * @returns {'epoch'|'step'|'iteration'|'round'}
 */
export function latestCounter(frames) {
  for (let i = (frames?.length ?? 0) - 1; i >= 0; i--) {
    const counter = frames[i]?.counter;
    if (counter && WORDS[counter]) return counter;
  }
  return 'epoch';
}

/** The counter of one frame. */
export function frameCounter(frame) {
  return frame?.counter && WORDS[frame.counter] ? frame.counter : 'epoch';
}

/**
 * The counter's name in English, where the dashboard's own text is English.
 *
 * `one` and `many` name it ("step", "steps"), `title` opens a label
 * ("Step"), `short` fits a chip ("ep", "iter"). `readings` is for a count of
 * readings, or the change from one to the next: an epoch for a run read once
 * an epoch, and "readings" for any other — a run told every 250 steps has
 * nine readings, not nine steps.
 *
 * @param {string|null|undefined} counter
 * @param {'one'|'many'|'short'|'title'|'readings'} [form]
 */
export function counterWord(counter, form = 'one') {
  return (WORDS[counter] ?? WORDS.epoch)[form];
}

/** The counter's name in the reader's language, for a label ("Epoch", "Étape"). */
export function counterLabel(counter) {
  switch (counter) {
    case 'step': return t('labels.step', 'Step');
    case 'iteration': return t('labels.iteration', 'Iteration');
    case 'round': return t('labels.round', 'Round');
    default: return t('labels.epoch', 'Epoch');
  }
}

/** One counter for several runs' frames, or null when they do not share one. */
export function sharedCounter(frameLists) {
  const kinds = new Set((frameLists ?? []).map((frames) => latestCounter(frames)));
  return kinds.size === 1 ? [...kinds][0] : null;
}
