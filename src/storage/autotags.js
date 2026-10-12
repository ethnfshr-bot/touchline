import { ACT } from '../engine/actions.js';
import { retimeEvents } from '../engine/videotime.js';
import { halfLen } from '../engine/stats.js';

/*
 * Automatic tags produced by the Touchline video tool (pipeline/). File shape:
 *   {
 *     app: 'touchline-auto', schema: 1,
 *     video: { name },                    the analysed video file
 *     sync: { k1, k2?, ht?, ft? },        video seconds: kick-offs, half-time, full-time
 *     events: [{ vt, team, type, x, y, conf? }],
 *     shape?: { us, them, territory_us_frame?, possession_share_us? }   positional.py summary
 *     generator: { version, ... }         free-form provenance
 *   }
 * Event coordinates use Touchline's frame (0-100, acting team attacking x = 100).
 */
export const AUTO_SCHEMA = 1;

export class AutoTagError extends Error {}

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const fail = (m) => {
  throw new AutoTagError(m);
};

/** Validate an automatic tags file. Returns the parsed object. */
export function parseAutoTags(input) {
  let d = input;
  if (typeof input === 'string') {
    try {
      d = JSON.parse(input);
    } catch {
      fail("This file isn't valid JSON.");
    }
  }
  if (!d || d.app !== 'touchline-auto') fail("This isn't an automatic tags file from the Touchline video tool.");
  if (d.schema !== AUTO_SCHEMA) fail('This automatic tags file is from a different version of the video tool.');
  const s = d.sync || {};
  for (const k of ['k1', 'k2', 'ht', 'ft']) if (s[k] != null && !(isNum(s[k]) && s[k] >= 0)) fail(`Invalid ${k} time.`);
  if (!Array.isArray(d.events)) fail('No events in this file.');
  d.events.forEach((e, i) => {
    const w = `Automatic event ${i + 1}`;
    if (!e || !isNum(e.vt) || e.vt < 0) fail(`${w} has an invalid video time.`);
    if (e.team !== 'us' && e.team !== 'them') fail(`${w} has an invalid team.`);
    if (!Object.prototype.hasOwnProperty.call(ACT, e.type)) fail(`${w} has an unknown type.`);
    if (!isNum(e.x) || !isNum(e.y) || e.x < 0 || e.x > 100 || e.y < 0 || e.y > 100) fail(`${w} has an invalid position.`);
  });
  return d;
}

/**
 * Merge automatic tags into a match, returning a new match object.
 * Previous automatic events are replaced; hand-tagged events are kept.
 * Kick-off marks from the file are used unless the match already has them.
 */
export function mergeAutoTags(match, auto, mkid) {
  const prevVideo = match.video || { source: 'file', name: auto.video && auto.video.name };
  const video = { ...prevVideo };
  const s = auto.sync || {};
  if (video.k1 == null && s.k1 != null) video.k1 = s.k1;
  if (video.k2 == null && s.k2 != null) video.k2 = s.k2;
  if (s.ht != null) video.ht = s.ht;
  if (s.ft != null) video.ft = s.ft;
  const kept = match.events.filter((e) => !e.auto);
  const added = auto.events.map((e) => {
    const ev = { id: mkid(), t: 0, vt: e.vt, team: e.team, type: e.type, x: e.x, y: e.y, auto: 1 };
    if (isNum(e.conf)) ev.conf = Math.round(e.conf * 100) / 100;
    return ev;
  });
  const events = retimeEvents([...kept, ...added], video, halfLen(match));
  const merged = { ...match, video, events, autoInfo: { ...(auto.generator || {}), importedAt: new Date().toISOString(), count: added.length } };
  if (auto.shape && typeof auto.shape === 'object') merged.shape = sanitiseShape(auto.shape);
  return merged;
}

const SHAPE_KEYS = ['height', 'width', 'depth', 'area', 'line', 'seconds'];

/** Keep only known numeric fields from a positional summary. */
function sanitiseShape(s) {
  const block = (b) => {
    if (!b || typeof b !== 'object') return null;
    const o = {};
    for (const k of SHAPE_KEYS) if (isNum(b[k])) o[k] = b[k];
    return Object.keys(o).length ? o : null;
  };
  const side = (x) =>
    x && typeof x === 'object'
      ? { overall: block(x.overall), in_possession: block(x.in_possession), out_of_possession: block(x.out_of_possession), coverage: isNum(x.coverage) ? x.coverage : null }
      : null;
  const out = { us: side(s.us), them: side(s.them) };
  const t = s.territory_us_frame;
  if (t && ['defensive_third', 'middle_third', 'attacking_third'].every((k) => isNum(t[k]))) {
    out.territory = { defensive: t.defensive_third, middle: t.middle_third, attacking: t.attacking_third };
  }
  if (isNum(s.possession_share_us)) out.possession = s.possession_share_us;
  return out;
}
