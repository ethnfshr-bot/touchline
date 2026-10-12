import { describe, expect, it } from 'vitest';
import { AutoTagError, mergeAutoTags, parseAutoTags } from '../src/storage/autotags.js';
import { ev, makeMatch } from './fixtures.js';

const auto = () => ({
  app: 'touchline-auto',
  schema: 1,
  video: { name: 'match.mp4' },
  sync: { k1: 145, k2: 3100, ht: 2900, ft: 6000 },
  events: [
    { vt: 145 + 600, team: 'them', type: 'off', x: 85, y: 40, conf: 0.734 },
    { vt: 3100 + 120, team: 'us', type: 'saved', x: 90, y: 55 },
  ],
  generator: { version: '0.1.0' },
});

let n = 0;
const mkid = () => 'a' + n++;

describe('parseAutoTags', () => {
  it('accepts a valid file', () => {
    expect(parseAutoTags(JSON.stringify(auto())).events).toHaveLength(2);
  });

  it('rejects other files and bad events', () => {
    expect(() => parseAutoTags('{"app":"touchline"}')).toThrow(AutoTagError);
    const bad = auto();
    bad.events[0].type = 'wondergoal';
    expect(() => parseAutoTags(bad)).toThrow('unknown type');
    const bad2 = auto();
    bad2.events[1].x = -5;
    expect(() => parseAutoTags(bad2)).toThrow('invalid position');
    const bad3 = auto();
    bad3.sync.k1 = 'soon';
    expect(() => parseAutoTags(bad3)).toThrow('Invalid k1');
  });
});

describe('mergeAutoTags', () => {
  it('adds automatic events timed from the video sync', () => {
    const m = mergeAutoTags(makeMatch({ events: [] }), auto(), mkid);
    expect(m.events.map((e) => [e.team, e.type, e.t, e.auto])).toEqual([
      ['them', 'off', 600, 1],
      ['us', 'saved', 45 * 60 + 120, 1],
    ]);
    expect(m.video).toMatchObject({ k1: 145, k2: 3100, ht: 2900, ft: 6000 });
    expect(m.events[0].conf).toBe(0.73);
    expect(m.autoInfo.count).toBe(2);
  });

  it('keeps hand tags and replaces earlier automatic ones', () => {
    const start = makeMatch({ events: [ev('us', 'pass', { t: 30 }), ev('us', 'goal', { t: 50, auto: 1 })] });
    const m = mergeAutoTags(start, auto(), mkid);
    expect(m.events.filter((e) => !e.auto)).toHaveLength(1);
    expect(m.events.filter((e) => e.auto)).toHaveLength(2);
  });

  it("keeps the user's own kick-off marks", () => {
    const start = makeMatch({ events: [], video: { source: 'file', name: 'match.mp4', k1: 150 } });
    const m = mergeAutoTags(start, auto(), mkid);
    expect(m.video.k1).toBe(150);
    expect(m.events[0].t).toBe(595);
  });
});
