/**
 * "Training complete" only for a run whose record says it finished.
 *
 * The timeline showed it whenever the page was not marked live — and a page
 * sets the run a moment before it marks it live, so every live run opened in
 * the dashboard read "Training complete" while it was still training.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import { createStore, markRunFinished, store } from '../store.js';
import { TimelineStory } from '../visualizations/TimelineStory.js';

function mounted(s) {
  const el = document.createElement('div');
  new TimelineStory(el).mount(s);
  return el;
}

const said = (el) => el.textContent.includes('Training complete');

describe('the Training complete card', () => {
  it('is not shown for a live run, in the moment before it is marked live', () => {
    // main.js: store.set({ run, … }) first, then store.set({ live: true }).
    const s = createStore({ run: null, live: false, milestones: [] });
    const el = mounted(s);
    s.set({ run: { id: 'r', finished_at: null } });
    s.set({ live: true });
    expect(said(el)).toBe(false);
  });

  it('is shown for a finished run', () => {
    const s = createStore({ run: null, live: false, milestones: [] });
    const el = mounted(s);
    s.set({ run: { id: 'r', finished_at: '2026-10-29T12:00:00Z', story_summary: 'Done.' } });
    expect(said(el)).toBe(true);
    expect(el.textContent).toContain('Done.');
  });

  describe('when the stream ends', () => {
    beforeEach(() => store.set({ run: { id: 'r', finished_at: null }, live: true, milestones: [] }));

    it('marks the run finished, with the summary the stream sent', () => {
      const el = mounted(store);
      expect(said(el)).toBe(false);
      markRunFinished({ final_grade: 'A', story_summary: 'Epoch 20: accuracy 95.8%.' });
      expect(store.get().run.finished_at).toBeTruthy();
      expect(store.get().live).toBe(false);
      expect(said(el)).toBe(true);
      expect(el.textContent).toContain('Epoch 20: accuracy 95.8%.');
    });
  });
});
