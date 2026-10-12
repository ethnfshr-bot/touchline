import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it } from 'vitest';
import { closeDB, deleteMatch, loadAll, putMatch, putRoster, replaceAll } from '../src/storage/db.js';
import { ImportError, SCHEMA_VERSION, mergeData, parseImport, toExport } from '../src/storage/io.js';
import { makeMatch, roster } from './fixtures.js';

const data = () => ({ roster: structuredClone(roster), matches: { m1: makeMatch() } });

describe('JSON export/import', () => {
  it('round-trips all data', () => {
    const d = data();
    const text = JSON.stringify(toExport(d));
    expect(parseImport(text)).toEqual(d);
  });

  it('stamps the app name and schema version', () => {
    const out = toExport(data(), new Date('2026-10-12T00:00:00Z'));
    expect(out).toMatchObject({ app: 'touchline', schema: SCHEMA_VERSION, exportedAt: '2026-10-12T00:00:00.000Z' });
  });

  it('fills in missing optional fields', () => {
    const exp = toExport(data());
    delete exp.matches[0].minutes;
    delete exp.matches[0].lineup;
    const m = parseImport(exp).matches.m1;
    expect(m.minutes).toEqual({});
    expect(m.lineup).toEqual({});
  });

  const rejects = (mutate, msg) => {
    const exp = JSON.parse(JSON.stringify(toExport(data())));
    mutate(exp);
    expect(() => parseImport(exp)).toThrow(ImportError);
    expect(() => parseImport(exp)).toThrow(msg);
  };

  it('rejects files that are not Touchline exports', () => {
    expect(() => parseImport('not json')).toThrow("isn't valid JSON");
    expect(() => parseImport('{"hello":1}')).toThrow("isn't a Touchline export");
  });

  it('rejects exports from a newer version', () => {
    rejects((e) => (e.schema = SCHEMA_VERSION + 1), 'newer version');
  });

  it('rejects malformed events', () => {
    rejects((e) => (e.matches[0].events[0].type = 'nutmeg'), 'unknown type "nutmeg"');
    rejects((e) => (e.matches[0].events[0].team = 'ref'), 'invalid team');
    rejects((e) => (e.matches[0].events[0].x = 140), 'invalid position');
    rejects((e) => (e.matches[0].events[0].t = -1), 'invalid time');
    rejects((e) => delete e.matches[0].events[0].id, 'has no id');
  });

  it('rejects malformed players and matches', () => {
    rejects((e) => delete e.roster[0].id, 'Player 1');
    rejects((e) => delete e.matches[0].events, 'no event list');
  });

  it('accepts optional video details and video times', () => {
    const exp = toExport(data());
    exp.matches[0].video = { source: 'youtube', youtubeId: 'dQw4w9WgXcQ', k1: 180, k2: 3120 };
    exp.matches[0].events[0].vt = 200.5;
    expect(parseImport(exp).matches.m1.video.k2).toBe(3120);
  });

  it('rejects malformed video details', () => {
    rejects((e) => (e.matches[0].video = { source: 'vimeo' }), 'unknown video source');
    rejects((e) => (e.matches[0].video = { source: 'youtube', youtubeId: '"><script>' }), 'invalid YouTube video id');
    rejects((e) => (e.matches[0].video = { source: 'file', name: 'a.mp4', k1: -3 }), 'invalid kick-off times');
    rejects((e) => (e.matches[0].events[0].vt = 'soon'), 'invalid video time');
  });

  it('does not accept inherited properties as event types', () => {
    rejects((e) => (e.matches[0].events[0].type = 'toString'), 'unknown type');
  });
});

describe('mergeData', () => {
  it('adds new records and replaces ones with the same id', () => {
    const current = data();
    const incoming = {
      roster: [{ id: 'gk', name: 'New Keeper', pos: 'GK' }, { id: 'new', name: 'Signing', pos: 'FWD' }],
      matches: { m1: makeMatch({ opp: 'Renamed' }), m2: makeMatch({ id: 'm2' }) },
    };
    const out = mergeData(current, incoming);
    expect(out.roster).toHaveLength(roster.length + 1);
    expect(out.roster.find((p) => p.id === 'gk').name).toBe('New Keeper');
    expect(Object.keys(out.matches)).toEqual(['m1', 'm2']);
    expect(out.matches.m1.opp).toBe('Renamed');
    expect(current.roster.find((p) => p.id === 'gk').name).toBe('Keeper'); // input untouched
  });
});

describe('IndexedDB storage', () => {
  afterEach(async () => {
    await closeDB();
    await new Promise((resolve) => {
      const r = indexedDB.deleteDatabase('touchline');
      r.onsuccess = r.onerror = resolve;
    });
  });

  it('starts empty', async () => {
    expect(await loadAll()).toEqual({ roster: [], matches: {} });
  });

  it('saves and loads matches and the roster', async () => {
    await putRoster(roster);
    await putMatch(makeMatch());
    await closeDB(); // force a fresh connection
    expect(await loadAll()).toEqual({ roster, matches: { m1: makeMatch() } });
  });

  it('deletes a match', async () => {
    await putMatch(makeMatch());
    await putMatch(makeMatch({ id: 'm2' }));
    await deleteMatch('m1');
    expect(Object.keys((await loadAll()).matches)).toEqual(['m2']);
  });

  it('replaces everything', async () => {
    await putMatch(makeMatch({ id: 'old' }));
    await replaceAll(data());
    const out = await loadAll();
    expect(Object.keys(out.matches)).toEqual(['m1']);
    expect(out.roster).toEqual(roster);
  });
});
