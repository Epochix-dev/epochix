/**
 * A reinforcement-learning run is told by its mean episode reward, and the
 * "In plain English" panel says so by that name — never as an accuracy, a
 * percentage or answers right on unseen data — and counts its iterations as
 * iterations.
 *
 * The rewards are the recorded PPO run's own (tests/fixtures/logs/
 * sb3_ppo_real.log): 21.2 to 395 over 25 iterations.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

import { Educational } from '../visualizations/Educational.js';
import { metricLabel } from '../viz-util.js';

const REPO = path.resolve(__dirname, '../../..');

/** Every table's (iteration, mean episode reward), read from the recording. */
function ppoRewards() {
  const text = fs.readFileSync(path.join(REPO, 'tests/fixtures/logs/sb3_ppo_real.log'), 'utf8');
  const rewards = [...text.matchAll(/^\|    ep_rew_mean +\| (\S{1,20}) +\|/gm)].map((m) => Number(m[1]));
  const iterations = [...text.matchAll(/^\|    iterations +\| (\S{1,20}) +\|/gm)].map((m) => Number(m[1]));
  return rewards.map((value, i) => ({ epoch: iterations[i], value }));
}

function plain(points) {
  const frames = points.map((p, i) => ({
    seq: i, epoch: p.epoch, counter: 'iteration', primary_metric: 'ep_rew_mean',
    primary_metric_value: p.value, grade: 'A+', phase: 'polishing',
  }));
  const el = document.createElement('div');
  const state = { frames, metrics: [], run: { primary_metric: 'val_loss', task_type: 'reinforcement' } };
  new Educational(el).mount({ get: () => state, subscribe: () => () => {} });
  return el.textContent.replace(/\s+/g, ' ');
}

describe('a reinforcement-learning run in plain English', () => {
  it('reads the recording: 25 iterations, 21.2 to 395', () => {
    const points = ppoRewards();
    expect(points).toHaveLength(25);
    expect(points[0]).toEqual({ epoch: 1, value: 21.2 });
    expect(points[24]).toEqual({ epoch: 25, value: 395 });
  });

  it('names the mean episode reward, and nothing it is not', () => {
    const text = plain(ppoRewards());
    expect(text).toContain('Over 25 iterations its mean episode reward went from 21.200 to 395.000');
    expect(text).not.toMatch(/accuracy|%|right on data|epoch/i);
  });

  it('labels the reward and the episode length by what they are', () => {
    expect(metricLabel('ep_rew_mean')).toBe('mean episode reward');
    expect(metricLabel('ep_len_mean')).toBe('mean episode length');
  });
});
