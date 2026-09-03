/**
 * A frame's cards belong to that frame.
 *
 * The render was guarded by `if (mc && frame?.metaphor_cards?.length)`, so a
 * frame carrying an EMPTY list skipped the block entirely and left whatever the
 * previous frame had rendered sitting in the DOM. An empty list means this
 * frame has no cards, not "keep the old ones".
 *
 * Seen live: a run that ended with a divergence frame displayed a stale
 * "Grade B+" card immediately beside the "Grade F" the same screen had just
 * given it.
 */
import { describe, it, expect, beforeEach } from 'vitest';

/** The render logic under test, matching JourneyPanel's card block. */
function renderCards(mc, frame) {
  if (mc && !frame?.metaphor_cards?.length) {
    mc.innerHTML = '';
  } else if (mc) {
    mc.innerHTML = frame.metaphor_cards
      .slice(0, 4)
      .map(
        (c) =>
          `<div class="metaphor-card"><div class="mc-title">${c.title ?? ''}</div>` +
          `<div class="mc-body">${c.body ?? ''}</div></div>`,
      )
      .join('');
  }
}

describe('metaphor cards', () => {
  let mc;

  beforeEach(() => {
    document.body.innerHTML = '<div id="metaphor-cards"></div>';
    mc = document.getElementById('metaphor-cards');
  });

  it('renders the cards a frame carries', () => {
    renderCards(mc, {
      metaphor_cards: [
        { title: 'Phase', body: 'Learning' },
        { title: 'Grade', body: 'B+' },
      ],
    });
    expect(mc.querySelectorAll('.metaphor-card')).toHaveLength(2);
    expect(mc.textContent).toContain('B+');
  });

  it('clears the previous frame’s cards when a frame has none', () => {
    renderCards(mc, { metaphor_cards: [{ title: 'Grade', body: 'B+' }] });
    expect(mc.textContent).toContain('B+');

    renderCards(mc, { metaphor_cards: [] });
    expect(mc.querySelectorAll('.metaphor-card')).toHaveLength(0);
    expect(mc.textContent).not.toContain('B+');
  });

  it('clears when the field is missing entirely', () => {
    renderCards(mc, { metaphor_cards: [{ title: 'Grade', body: 'B+' }] });
    renderCards(mc, { seq: 9 });
    expect(mc.textContent).not.toContain('B+');
  });

  it('a later frame replaces an earlier grade rather than joining it', () => {
    renderCards(mc, { metaphor_cards: [{ title: 'Grade', body: 'B+' }] });
    renderCards(mc, { metaphor_cards: [{ title: 'Grade', body: 'F' }] });
    expect(mc.textContent).toContain('F');
    expect(mc.textContent).not.toContain('B+');
  });
});
