import { describe, expect, it } from 'vitest';
import { chronMatches, involved, minsOf, playerStats, posGroup, posPlayed, score, sortedMatches, teamStats, thirds } from '../src/engine/stats.js';
import { XG_EDGE_OF_BOX, XG_PEN_SPOT, ev, makeMatch, roster } from './fixtures.js';

const P = Object.fromEntries(roster.map((p) => [p.id, p]));

describe('score', () => {
  it('counts goals per side', () => {
    expect(score(makeMatch())).toEqual([1, 1]);
    expect(score(makeMatch({ events: [] }))).toEqual([0, 0]);
  });
});

describe('teamStats', () => {
  const m = makeMatch();
  const us = teamStats(m, 'us');

  it('counts shots, shots on target and goals', () => {
    expect(us.shots).toBe(2);
    expect(us.sot).toBe(2);
    expect(us.goals).toBe(1);
  });

  it('sums xG over shots', () => {
    expect(us.xg).toBeCloseTo(XG_PEN_SPOT + XG_EDGE_OF_BOX, 10);
    expect(teamStats(m, 'them').xg).toBeCloseTo(XG_PEN_SPOT, 10);
  });

  it('treats an assisted shot as a completed key pass', () => {
    expect(us.kp).toBe(1);
    expect(us.passC).toBe(4); // 3 tagged passes + 1 assist
    expect(us.passA).toBe(5); // + 1 lost pass
  });

  it('counts on-ball actions and final-third touches', () => {
    expect(us.onball).toBe(8); // 7 on-ball events + 1 implied assist pass
    expect(us.ft).toBe(3); // goal, saved shot and touch are all at x >= 66.67
  });

  it('counts defensive actions', () => {
    expect(us.tkl).toBe(1);
    expect(us.int).toBe(1);
  });

  it('counts big chances missed', () => {
    const mm = makeMatch({ events: [ev('us', 'off', { big: 1 }), ev('us', 'goal', { big: 1 })] });
    const s = teamStats(mm, 'us');
    expect(s.big).toBe(2);
    expect(s.bigMiss).toBe(1);
  });
});

describe('thirds', () => {
  it('flips opposition events into our attacking direction', () => {
    // Us: 4 actions at x=50 (middle), 3 at x>=70 (attacking).
    // Them: goal at x=89.5 and pass at x=70 in their frame -> our defensive third.
    expect(thirds(makeMatch())).toEqual([[0, 2], [4, 0], [3, 0]]);
  });

  it('ignores off-the-ball actions', () => {
    expect(thirds(makeMatch({ events: [ev('us', 'tackle'), ev('us', 'clr')] }))).toEqual([[0, 0], [0, 0], [0, 0]]);
  });
});

describe('playerStats', () => {
  const m = makeMatch();

  it('credits the assister with assist, xA, key pass and a completed pass', () => {
    const s = playerStats(m, 'mid');
    expect(s.assists).toBe(1);
    expect(s.xa).toBeCloseTo(XG_PEN_SPOT, 10);
    expect(s.kp).toBe(1);
    expect(s.passC).toBe(4);
    expect(s.passL).toBe(1);
    expect(s.touches).toBe(5);
    expect(s.actions).toBe(5);
  });

  it('credits the shooter with goals, xG and shots', () => {
    const s = playerStats(m, 'fwd');
    expect(s.goals).toBe(1);
    expect(s.shots).toBe(2);
    expect(s.sot).toBe(2);
    expect(s.xg).toBeCloseTo(XG_PEN_SPOT + XG_EDGE_OF_BOX, 10);
    expect(s.touches).toBe(3);
  });

  it('ignores opposition events', () => {
    const mm = makeMatch({ events: [ev('them', 'goal', { pid: 'fwd' })] });
    expect(playerStats(mm, 'fwd').goals).toBe(0);
  });
});

describe('minsOf', () => {
  const m = makeMatch();

  it('uses an explicit minutes override first', () => {
    expect(minsOf(m, 'def')).toBe(75);
  });

  it('uses lineup on/off times', () => {
    expect(minsOf(m, 'gk')).toBe(90); // started, played to full time
    expect(minsOf(m, 'mid')).toBe(80); // subbed off at 80
    expect(minsOf(m, 'sub')).toBe(30); // came on at 60
  });

  it('respects half length', () => {
    expect(minsOf(makeMatch({ half: 30 }), 'gk')).toBe(60);
  });

  it('gives the full match when no lineup was recorded', () => {
    const noLineup = makeMatch({ lineup: {} });
    expect(minsOf(noLineup, 'fwd')).toBe(90);
    expect(minsOf(noLineup, 'bench')).toBe(90); // blank override is ignored
  });

  it('estimates minutes for a player missing from a recorded lineup', () => {
    // Forward's first action is at 10': assumed to have started, so the full match.
    expect(minsOf(m, 'fwd')).toBe(90);
    // An unrecorded sub tagged once at 80' gets 10 minutes, not 90.
    const late = makeMatch({ events: [ev('us', 'pass', { pid: 'bench', t: 80 * 60 })] });
    expect(minsOf(late, 'bench')).toBe(10);
    // First action at 62': on from then to full time.
    const sub = makeMatch({ events: [ev('us', 'pass', { pid: 'bench', t: 62 * 60 }), ev('us', 'pass', { pid: 'bench', t: 70 * 60 })] });
    expect(minsOf(sub, 'bench')).toBe(28);
    // Assists count as actions too.
    const ast = makeMatch({ events: [ev('us', 'goal', { pid: 'fwd', ast: 'bench', t: 75 * 60 })] });
    expect(minsOf(ast, 'bench')).toBe(15);
  });
});

describe('positions', () => {
  const m = makeMatch();
  it('prefers the lineup position over the squad position', () => {
    expect(posPlayed(m, P.mid)).toBe('AM');
    expect(posPlayed(m, P.def)).toBe('DEF');
    expect(posGroup(m, P.sub)).toBe('MID');
    expect(posGroup(m, P.gk)).toBe('GK');
    expect(posGroup(m, P.def)).toBe('DEF');
  });
});

describe('involved', () => {
  it('includes lineup players, players with actions and players given minutes', () => {
    expect(involved(makeMatch(), roster).map((p) => p.id)).toEqual(['gk', 'def', 'mid', 'fwd', 'sub']);
  });

  it('includes a player given minutes but no actions', () => {
    const m = makeMatch({ events: [], lineup: {}, minutes: { bench: 12 } });
    expect(involved(m, roster).map((p) => p.id)).toEqual(['bench']);
  });

  it('excludes a lineup entry marked as not playing', () => {
    const m = makeMatch({ events: [], minutes: {}, lineup: { gk: { pos: '', on: 5, off: '' } } });
    expect(involved(m, roster)).toEqual([]);
  });
});

describe('match ordering', () => {
  const a = { id: 'a', date: '2026-01-01', created: 1 };
  const b = { id: 'b', date: '2026-02-01', created: 2 };
  const c = { id: 'c', date: '2026-02-01', created: 3 };
  it('sorts newest first and chronologically', () => {
    expect(sortedMatches([a, b, c]).map((m) => m.id)).toEqual(['c', 'b', 'a']);
    expect(chronMatches([c, a, b]).map((m) => m.id)).toEqual(['a', 'b', 'c']);
  });
});
