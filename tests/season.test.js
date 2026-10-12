import { describe, expect, it } from 'vitest';
import { formationTable, onOffSplits, playerLog, positionSplits, seasonRows, teamSeason } from '../src/engine/season.js';
import { XG_PEN_SPOT, ev, makeMatch, roster } from './fixtures.js';

const m1 = makeMatch(); // 1–1, 4-4-2
const m2 = makeMatch({
  id: 'm2',
  date: '2026-09-13',
  formation: '4-3-3',
  minutes: {},
  lineup: { gk: { pos: 'GK', on: '', off: '' } },
  events: [ev('us', 'goal', { pid: 'fwd', t: 60, x: 89.5238, y: 50 }), ev('us', 'goal', { pid: 'fwd', t: 120, x: 89.5238, y: 50 })],
}); // 2–0
const m3 = makeMatch({ id: 'm3', date: '2026-09-20', formation: '4-4-2', minutes: {}, lineup: {}, events: [ev('them', 'goal', { t: 60 })] }); // 0–1
const season = [m1, m2, m3];

describe('seasonRows', () => {
  const rows = seasonRows(season, roster);
  const byId = Object.fromEntries(rows.map((r) => [r.p.id, r.a]));

  it('only includes players who appeared', () => {
    expect(Object.keys(byId).sort()).toEqual(['def', 'fwd', 'gk', 'mid', 'sub']);
  });

  it('sums appearances, minutes and goals', () => {
    expect(byId.fwd.apps).toBe(2);
    expect(byId.fwd.mins).toBe(180);
    expect(byId.fwd.goals).toBe(3);
    expect(byId.gk.apps).toBe(2);
  });

  it('averages match ratings', () => {
    // Keeper: 5.85 (conceded 1) then 6.4 (clean sheet).
    expect(byId.gk.rating).toBeCloseTo((5.85 + 6.4) / 2, 10);
  });

  it('sorts by average rating, best first', () => {
    const ratings = rows.map((r) => r.a.rating);
    expect(ratings).toEqual([...ratings].sort((a, b) => b - a));
    expect(rows[0].p.id).toBe('fwd');
  });
});

describe('teamSeason', () => {
  it('builds the record and points', () => {
    const t = teamSeason(season);
    expect([t.w, t.d, t.l, t.points]).toEqual([1, 1, 1, 4]);
    expect([t.gf, t.ga]).toEqual([3, 2]);
    expect(t.pairs).toHaveLength(3);
    expect(t.pairs[1][0]).toBeCloseTo(2 * XG_PEN_SPOT, 10);
  });
});

describe('formationTable', () => {
  it('groups by formation, most used first', () => {
    const rows = formationTable(season);
    expect(rows.map((r) => [r.formation, r.n, r.w, r.d, r.l])).toEqual([
      ['4-4-2', 2, 0, 1, 1],
      ['4-3-3', 1, 1, 0, 0],
    ]);
  });
});

describe('player splits', () => {
  it('groups by position played', () => {
    const p = roster.find((x) => x.id === 'mid');
    const splits = positionSplits(p, playerLog(p, season, roster));
    expect(splits.map((s) => [s.pos, s.n, s.mins])).toEqual([['AM', 1, 80]]);
  });

  it('splits team xG by whether the player was on the pitch', () => {
    // Sub comes on at 60'. One shot each side before, one of ours after.
    const m = makeMatch({
      minutes: {},
      lineup: { sub: { pos: 'CM', on: 60, off: '' } },
      events: [
        ev('us', 'off', { t: 10 * 60, x: 89.5238 }),
        ev('them', 'off', { t: 20 * 60, x: 89.5238 }),
        ev('us', 'goal', { t: 70 * 60, x: 89.5238 }),
      ],
    });
    const s = onOffSplits(roster.find((x) => x.id === 'sub'), [m], roster);
    expect(s.onM).toBe(30);
    expect(s.offM).toBe(60);
    expect(s.onF).toBeCloseTo(XG_PEN_SPOT, 10);
    expect(s.offF).toBeCloseTo(XG_PEN_SPOT, 10);
    expect(s.offA).toBeCloseTo(XG_PEN_SPOT, 10);
    expect(s.onA).toBe(0);
  });
});
