import { ACT } from '../engine/actions.js';
import { isYouTubeId } from '../engine/videosource.js';

/*
 * JSON export/import. The file format is versioned by `schema`. When the data
 * shape changes, bump SCHEMA_VERSION and add a step to MIGRATIONS that upgrades
 * the previous version, so old backups keep importing.
 */
export const SCHEMA_VERSION = 1;

/** MIGRATIONS[n] upgrades a schema-n file to schema n+1. */
const MIGRATIONS = {};

export class ImportError extends Error {}

export function toExport(data, now = new Date()) {
  return {
    app: 'touchline',
    schema: SCHEMA_VERSION,
    exportedAt: now.toISOString(),
    roster: data.roster,
    matches: Object.values(data.matches),
  };
}

const isStr = (v) => typeof v === 'string' && v.length > 0;
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

function fail(msg) {
  throw new ImportError(msg);
}

function checkEvent(e, where) {
  if (!e || typeof e !== 'object') fail(`${where} is not an object.`);
  if (!isStr(e.id)) fail(`${where} has no id.`);
  if (!isNum(e.t) || e.t < 0) fail(`${where} has an invalid time.`);
  if (e.team !== 'us' && e.team !== 'them') fail(`${where} has an invalid team.`);
  if (!Object.prototype.hasOwnProperty.call(ACT, e.type)) fail(`${where} has an unknown type "${e.type}".`);
  if (!isNum(e.x) || !isNum(e.y) || e.x < 0 || e.x > 100 || e.y < 0 || e.y > 100) fail(`${where} has an invalid position.`);
  if (e.vt != null && (!isNum(e.vt) || e.vt < 0)) fail(`${where} has an invalid video time.`);
}

const optTime = (v) => v == null || (isNum(v) && v >= 0);

function checkVideo(v, where) {
  if (v == null) return;
  if (typeof v !== 'object') fail(`${where} has invalid video details.`);
  if (v.source !== 'file' && v.source !== 'youtube') fail(`${where} has an unknown video source.`);
  if (v.source === 'youtube' && !isYouTubeId(v.youtubeId)) fail(`${where} has an invalid YouTube video id.`);
  if (!optTime(v.k1) || !optTime(v.k2)) fail(`${where} has invalid kick-off times.`);
  if (!optTime(v.ht) || !optTime(v.ft)) fail(`${where} has invalid half-time or full-time marks.`);
}

/**
 * Parse and validate an export file.
 * @param {string|object} input  file text or parsed JSON
 * @returns {{roster: object[], matches: Object<string, object>}}
 * @throws {ImportError} with a message that can be shown to the user
 */
export function parseImport(input) {
  let d = input;
  if (typeof input === 'string') {
    try {
      d = JSON.parse(input);
    } catch {
      fail("This file isn't valid JSON.");
    }
  }
  if (!d || typeof d !== 'object' || d.app !== 'touchline') fail("This isn't a Touchline export.");
  if (!Number.isInteger(d.schema) || d.schema < 1) fail('This export has no schema version.');
  if (d.schema > SCHEMA_VERSION) fail('This export was made by a newer version of Touchline. Update the app and try again.');
  for (let v = d.schema; v < SCHEMA_VERSION; v++) d = MIGRATIONS[v](d);

  if (!Array.isArray(d.roster)) fail('The export has no squad list.');
  if (!Array.isArray(d.matches)) fail('The export has no match list.');

  const roster = d.roster.map((p, i) => {
    if (!p || !isStr(p.id) || typeof p.name !== 'string') fail(`Player ${i + 1} is missing an id or name.`);
    return p;
  });

  const matches = {};
  d.matches.forEach((m, i) => {
    const where = `Match ${i + 1}`;
    if (!m || !isStr(m.id)) fail(`${where} has no id.`);
    if (!Array.isArray(m.events)) fail(`${where} has no event list.`);
    m.events.forEach((e, j) => checkEvent(e, `${where}, event ${j + 1}`));
    checkVideo(m.video, where);
    matches[m.id] = { minutes: {}, lineup: {}, ...m };
  });

  return { roster, matches };
}

/** Merge imported data into current data. Records with the same id are replaced by the imported copy. */
export function mergeData(current, incoming) {
  const roster = current.roster.slice();
  incoming.roster.forEach((p) => {
    const i = roster.findIndex((x) => x.id === p.id);
    if (i >= 0) roster[i] = p;
    else roster.push(p);
  });
  return { roster, matches: { ...current.matches, ...incoming.matches } };
}
