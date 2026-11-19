/**
 * Milestones reach the timeline from a loaded run, not only from a live one.
 *
 * They were read only from the live `milestone` message, so a page opened on
 * a run, and every HTML export, showed none. A frame now carries its own, the
 * snapshot (and an export's inline data) lists them all, including the ones a
 * run ends with, and the same milestone arriving by more than one of these
 * ways is held once.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import { pushFrame, pushMilestone, store } from '../store.js';
import { TimelineStory } from '../visualizations/TimelineStory.js';

const RUN = '01RUN';
const ms = (seq, kind, epoch, message) => ({ run_id: RUN, seq, kind, epoch, value: 0.5, message });
const frame = (seq, epoch, milestones = []) => ({
  run_id: RUN, seq, epoch, grade: 'B', phase: 'learning', narrative: `epoch ${epoch}`,
  warnings: [], milestones,
});

// The shape /api/snapshot/{id} returns for a finished run.
const SNAPSHOT = {
  frames: [
    frame(1, 1, [ms(1, 'best_so_far', 1, 'New best: 0.0540')]),
    frame(33, 17, [ms(33, 'first_above_25', 17, 'Crossed 25%: 0.2540')]),
    frame(53, 27, [
      ms(53, 'first_above_50', 27, 'Crossed 50%: 0.5149'),
      ms(53, 'biggest_jump', 27, 'Biggest single-epoch improvement: 0.0417'),
    ]),
  ],
  milestones: [
    ms(1, 'best_so_far', 1, 'New best: 0.0540'),
    ms(33, 'first_above_25', 17, 'Crossed 25%: 0.2540'),
    ms(53, 'first_above_50', 27, 'Crossed 50%: 0.5149'),
    ms(53, 'biggest_jump', 27, 'Biggest single-epoch improvement: 0.0417'),
    ms(100, 'training_complete', 50, 'Training completed.'),
  ],
};

function load(snapshot) {
  for (const f of snapshot.frames) pushFrame(f);
  for (const m of snapshot.milestones) pushMilestone(m);
}

beforeEach(() => {
  store.set({
    run: { id: RUN, finished_at: '2026-11-19T10:00:00Z', story_summary: 'Done.' },
    frames: [], currentFrame: null, scrubEpoch: -1, warnings: [], warningLog: [],
    milestones: [], live: false,
  });
});

describe('a loaded run', () => {
  it('holds every milestone once, frames\' and the run\'s final ones', () => {
    load(SNAPSHOT);
    expect(store.get().milestones.map((m) => `${m.seq}:${m.kind}`)).toEqual([
      '1:best_so_far',
      '33:first_above_25',
      '53:first_above_50',
      '53:biggest_jump',
      '100:training_complete',
    ]);
  });

  it('takes a live frame\'s milestones, and not again from the message that follows', () => {
    pushFrame(frame(53, 27, [ms(53, 'first_above_50', 27, 'Crossed 50%: 0.5149')]));
    expect(store.get().milestones.map((m) => m.kind)).toEqual(['first_above_50']);
    pushMilestone(ms(53, 'first_above_50', 27, 'Crossed 50%: 0.5149'));
    expect(store.get().milestones).toHaveLength(1);
  });

  it('keeps milestones without a seq apart, by epoch and message', () => {
    pushMilestone({ kind: 'best_so_far', epoch: 3, message: 'New best: 0.5000' });
    pushMilestone({ kind: 'best_so_far', epoch: 7, message: 'New best: 0.7000' });
    pushMilestone({ kind: 'best_so_far', epoch: 7, message: 'New best: 0.7000' });
    expect(store.get().milestones.map((m) => m.epoch)).toEqual([3, 7]);
  });
});

describe('the timeline of a loaded run', () => {
  function mounted() {
    const el = document.createElement('div');
    new TimelineStory(el).mount(store);
    return el;
  }

  it('shows each milestone, by its message', () => {
    const el = mounted();
    load(SNAPSHOT);
    for (const text of ['New best: 0.0540', 'Crossed 25%: 0.2540', 'Crossed 50%: 0.5149',
      'Biggest single-epoch improvement: 0.0417']) {
      expect(el.textContent).toContain(text);
    }
  });

  it('says the run finished once, not twice', () => {
    const el = mounted();
    load(SNAPSHOT);
    expect(el.textContent).toContain('Done.');
    expect(el.textContent).not.toContain('Training completed.');
    const cards = [...el.querySelectorAll('.tc-title')].map((n) => n.textContent);
    expect(cards.filter((t) => /training complete/i.test(t))).toHaveLength(1);
  });
});
