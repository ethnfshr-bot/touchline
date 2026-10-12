import { describe, expect, it } from 'vitest';
import { matchSummary } from '../src/engine/summary.js';
import { ev, makeMatch, roster } from './fixtures.js';

const shot = (team, type, x = 89.5238, extra = {}) => ev(team, type, { x, y: 50, ...extra });

describe('matchSummary', () => {
  it('says nothing when there is nothing to summarise', () => {
    expect(matchSummary(makeMatch({ events: [] }), roster)).toEqual([]);
  });

  it('calls even chances even', () => {
    const s = matchSummary(makeMatch(), roster, 'Boulder FC');
    expect(s[0]).toMatch(/^It finished 1–1\. Chances were even/);
  });

  it('flags a defeat against the run of play', () => {
    const m = makeMatch({ events: [shot('us', 'saved', 97), shot('us', 'off', 96), shot('us', 'saved', 95), shot('them', 'goal', 60), shot('them', 'goal', 62)] });
    const s = matchSummary(m, roster, 'Boulder FC');
    expect(s[0]).toMatch(/You lost 0–2, and you created the better chances .* not a fair reflection/);
    expect(s.join(' ')).toMatch(/Boulder FC scored more than their chances deserved/);
  });

  it('notices wasteful finishing and missed big chances', () => {
    const m = makeMatch({ events: [shot('us', 'off', 97, { big: 1 }), shot('us', 'saved', 97, { big: 1 }), shot('us', 'off', 96)] });
    const s = matchSummary(m, roster).join(' ');
    expect(s).toMatch(/Wasteful in front of goal/);
    expect(s).toMatch(/missed 2 big chances/);
  });

  it('names a player of the match when enough players are rated', () => {
    expect(matchSummary(makeMatch(), roster).join(' ')).toMatch(/Player of the match: Forward/);
  });
});
