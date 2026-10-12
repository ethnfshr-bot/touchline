import { describe, expect, it } from 'vitest';
import { BASE, matchRatings, rating, ratingBand } from '../src/engine/rating.js';
import { playerStats } from '../src/engine/stats.js';
import { XG_PEN_SPOT, makeMatch, roster } from './fixtures.js';

const zero = playerStats({ events: [] }, 'x');
const withStats = (s) => ({ ...zero, ...s });

describe('rating', () => {
  it('starts at 6.0', () => {
    expect(rating(zero, 'MID', 0, 90)).toBe(BASE);
  });

  it('needs at least 10 minutes', () => {
    expect(rating(zero, 'MID', 0, 9)).toBeNull();
    expect(rating(zero, 'MID', 0, 10)).toBe(BASE);
    expect(rating(zero, 'MID', 0, undefined)).toBeNull();
  });

  it('adds a point per goal and 0.6 per assist', () => {
    expect(rating(withStats({ goals: 1 }), 'FWD', 0, 90)).toBeCloseTo(7.0, 10);
    expect(rating(withStats({ assists: 1 }), 'FWD', 0, 90)).toBeCloseTo(6.6, 10);
  });

  it('penalises lost possession', () => {
    expect(rating(withStats({ disp: 5 }), 'MID', 0, 90)).toBeCloseTo(5.6, 10);
  });

  it('gives keepers and defenders a clean-sheet bonus after 60 minutes', () => {
    expect(rating(zero, 'GK', 0, 60)).toBeCloseTo(6.4, 10);
    expect(rating(zero, 'DEF', 0, 90)).toBeCloseTo(6.4, 10);
    expect(rating(zero, 'GK', 0, 59)).toBe(BASE);
    expect(rating(zero, 'MID', 0, 90)).toBe(BASE);
  });

  it('docks keepers and defenders 0.15 per goal conceded, capped at 4', () => {
    expect(rating(zero, 'DEF', 2, 90)).toBeCloseTo(5.7, 10);
    expect(rating(zero, 'GK', 4, 90)).toBeCloseTo(5.4, 10);
    expect(rating(zero, 'GK', 9, 90)).toBeCloseTo(5.4, 10);
    expect(rating(zero, 'FWD', 9, 90)).toBe(BASE);
  });

  it('clamps to [3, 10]', () => {
    expect(rating(withStats({ goals: 6 }), 'FWD', 0, 90)).toBe(10);
    expect(rating(withStats({ disp: 100 }), 'MID', 0, 90)).toBe(3);
  });
});

describe('ratingBand', () => {
  it('maps ratings to colour bands', () => {
    expect([8, 7.99, 7, 6.5, 5.9].map(ratingBand)).toEqual(['great', 'good', 'good', 'ok', 'bad']);
  });
});

describe('matchRatings', () => {
  const byId = Object.fromEntries(matchRatings(makeMatch(), roster).map((x) => [x.p.id, x]));

  it('rates every involved player', () => {
    expect(Object.keys(byId)).toEqual(['gk', 'def', 'mid', 'fwd', 'sub']);
  });

  it('applies goals conceded to the keeper', () => {
    expect(byId.gk.r).toBeCloseTo(5.85, 10);
  });

  it('combines the weighted stats', () => {
    // Forward: goal, 2 shots on target, xG from both shots.
    const fwd = byId.fwd.st;
    expect(byId.fwd.r).toBeCloseTo(6 + 1 + fwd.xg * 0.4 + 2 * 0.1, 10);
    // Midfielder: assist, xA, key pass, 4 completed and 1 lost pass.
    expect(byId.mid.r).toBeCloseTo(6 + 0.6 + XG_PEN_SPOT * 0.3 + 0.15 + 4 * 0.012 - 0.03, 10);
    // Defender: 75 minutes, 1 conceded, tackle + interception.
    expect(byId.def.r).toBeCloseTo(6 + 0.1 + 0.1 - 0.15, 10);
  });
});
