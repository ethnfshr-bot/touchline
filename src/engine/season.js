import { isShot } from './actions.js';
import { rating } from './rating.js';
import { halfLen, involved, minsOf, playerStats, posGroup, posPlayed, score, teamStats } from './stats.js';
import { avgOf, clamp } from './util.js';
import { xgOf } from './xg.js';

const SUM_KEYS = ['goals', 'assists', 'xg', 'xa', 'shots', 'sot', 'kp', 'passC', 'drbW', 'tklW', 'int', 'rec'];

/** Season totals per player who has appeared, sorted by average rating. */
export function seasonRows(matches, roster) {
  return roster
    .map((p) => {
      const a = { apps: 0, mins: 0, passA: 0, rs: [] };
      SUM_KEYS.forEach((k) => (a[k] = 0));
      matches.forEach((m) => {
        if (!involved(m, roster).find((x) => x.id === p.id)) return;
        const st = playerStats(m, p.id);
        const mn = minsOf(m, p.id);
        const r = rating(st, posGroup(m, p), score(m)[1], mn);
        a.apps++;
        a.mins += mn;
        SUM_KEYS.forEach((k) => (a[k] += st[k]));
        a.passA += st.passC + st.passL;
        if (r != null) a.rs.push(r);
      });
      a.rating = avgOf(a.rs);
      return { p, a };
    })
    .filter((x) => x.a.apps > 0)
    .sort((x, y) => (y.a.rating || 0) - (x.a.rating || 0));
}

/** Team record and xG totals. `matches` should be in chronological order. */
export function teamSeason(matches) {
  const t = { w: 0, d: 0, l: 0, gf: 0, ga: 0, xf: 0, xa: 0, pairs: [] };
  matches.forEach((m) => {
    const [u, o] = score(m);
    const A = teamStats(m, 'us');
    const B = teamStats(m, 'them');
    t.gf += u;
    t.ga += o;
    t.xf += A.xg;
    t.xa += B.xg;
    if (u > o) t.w++;
    else if (u === o) t.d++;
    else t.l++;
    t.pairs.push([A.xg, B.xg]);
  });
  t.points = t.w * 3 + t.d;
  return t;
}

/** Results and xG grouped by formation, most-used first. */
export function formationTable(matches) {
  const fm = {};
  matches.forEach((m) => {
    const k = m.formation || 'Not set';
    const [u, o] = score(m);
    const row = fm[k] || (fm[k] = { formation: k, n: 0, w: 0, d: 0, l: 0, xf: 0, xa: 0 });
    row.n++;
    if (u > o) row.w++;
    else if (u === o) row.d++;
    else row.l++;
    row.xf += teamStats(m, 'us').xg;
    row.xa += teamStats(m, 'them').xg;
  });
  return Object.values(fm).sort((a, b) => b.n - a.n);
}

/** One entry per match the player was involved in: { m, st, mn, r }. */
export function playerLog(p, matches, roster) {
  const log = [];
  matches.forEach((m) => {
    if (!involved(m, roster).find((x) => x.id === p.id)) return;
    const st = playerStats(m, p.id);
    const mn = minsOf(m, p.id);
    log.push({ m, st, mn, r: rating(st, posGroup(m, p), score(m)[1], mn) });
  });
  return log;
}

/** Per-position aggregates from a playerLog(), most minutes first. */
export function positionSplits(p, log) {
  const bp = {};
  log.forEach((x) => {
    const k = posPlayed(x.m, p);
    const o = bp[k] || (bp[k] = { pos: k, n: 0, mins: 0, rs: [], ga: 0, xg: 0 });
    o.n++;
    o.mins += x.mn;
    if (x.r != null) o.rs.push(x.r);
    o.ga += x.st.goals + x.st.assists;
    o.xg += x.st.xg;
  });
  return Object.values(bp)
    .sort((a, b) => b.mins - a.mins)
    .map((o) => ({ ...o, rating: avgOf(o.rs) }));
}

/** Team xG for and against with the player on and off the pitch. */
export function onOffSplits(p, matches, roster) {
  const s = { onM: 0, offM: 0, onF: 0, onA: 0, offF: 0, offA: 0 };
  matches.forEach((m) => {
    const T = halfLen(m) * 2;
    const l = m.lineup && m.lineup[p.id];
    let a = null;
    let b = null;
    if (l && l.pos) {
      a = Number(l.on) || 0;
      b = l.off !== '' && l.off != null ? Number(l.off) : T;
    } else if (involved(m, roster).find((x) => x.id === p.id)) {
      a = 0;
      b = Math.min(T, minsOf(m, p.id));
    }
    const span = a == null ? 0 : clamp(b - a, 0, T);
    s.onM += span;
    s.offM += T - span;
    m.events.forEach((e) => {
      if (!isShot(e)) return;
      const mn = e.t / 60;
      const on = a != null && mn >= a && mn < b;
      const g = xgOf(e);
      if (e.team === 'us') {
        if (on) s.onF += g;
        else s.offF += g;
      } else if (on) s.onA += g;
      else s.offA += g;
    });
  });
  return s;
}
