import { describe, expect, it } from 'vitest';
import { LOSSES, WINS, thirdTotals, zoneGrid, zoneInsights } from '../src/engine/zones.js';
import { ev, makeMatch } from './fixtures.js';

const at = (type, x, y, team = 'us') => ev(team, type, { x, y });

describe('zoneGrid', () => {
  it('counts our events by third and channel', () => {
    const m = makeMatch({ events: [at('passlost', 10, 10), at('passlost', 50, 50), at('disp', 90, 90), at('passlost', 10, 10, 'them'), at('tackle', 80, 50)] });
    expect(zoneGrid([m], LOSSES)).toEqual([[1, 0, 0], [0, 1, 0], [0, 0, 1]]);
    expect(zoneGrid([m], WINS)).toEqual([[0, 0, 0], [0, 0, 0], [0, 1, 0]]);
  });

  it('adds up across matches and skips events without a position', () => {
    const a = makeMatch({ events: [at('rec', 10, 50)] });
    const b = makeMatch({ events: [at('rec', 12, 50), { ...at('rec', 90, 50), noloc: 1 }] });
    expect(thirdTotals(zoneGrid([a, b], WINS))).toEqual([2, 0, 0]);
  });
});

describe('zoneInsights', () => {
  it('flags turnovers in the defensive third and high regains', () => {
    const losses = [[3, 1, 0], [1, 1, 1], [1, 0, 0]]; // 4/8 in defensive third
    const wins = [[1, 1, 1], [1, 1, 1], [1, 2, 1]]; // 4/10 in attacking third
    const s = zoneInsights(wins, losses).join(' ');
    expect(s).toMatch(/50% of your turnovers happen in your defensive third/);
    expect(s).toMatch(/40% of your ball recoveries in the attacking third/);
  });

  it('stays quiet with too little data', () => {
    expect(zoneInsights([[1, 0, 0], [0, 0, 0], [0, 0, 0]], [[2, 0, 0], [0, 0, 0], [0, 0, 0]])).toEqual([]);
  });
});
