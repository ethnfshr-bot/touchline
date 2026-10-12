import { GROUP, isOn, isShot } from './actions.js';
import { sum } from './util.js';
import { xgOf } from './xg.js';

/*
 * Data shapes (see CLAUDE.md for the full description):
 *   Player  { id, name, num, pos }                     pos is a POS group
 *   Match   { id, created, opp, date, comp, half, veo, formation, events[], minutes{}, lineup{} }
 *   Event   { id, t, team: 'us'|'them', type, x, y, pid?, ast?, header?, big?, pen? }
 */

/** [goals for, goals against]. */
export function score(m) {
  let us = 0;
  let them = 0;
  m.events.forEach((e) => {
    if (e.type === 'goal') {
      if (e.team === 'us') us++;
      else them++;
    }
  });
  return [us, them];
}

export function teamStats(m, team) {
  const ev = m.events.filter((e) => e.team === team);
  const c = (t) => ev.filter((e) => e.type === t).length;
  const shots = ev.filter(isShot);
  // An assisted shot implies a completed pass that wasn't tagged separately.
  const ast = shots.filter((e) => e.ast).length;
  const passC = c('pass') + ast;
  const passA = passC + c('passlost');
  return {
    xg: sum(shots, xgOf),
    shots: shots.length,
    sot: c('goal') + c('saved'),
    goals: c('goal'),
    big: shots.filter((e) => e.big).length,
    bigMiss: shots.filter((e) => e.big && e.type !== 'goal').length,
    passC,
    passA,
    kp: ast,
    onball: ev.filter(isOn).length + ast,
    ft: ev.filter((e) => isOn(e) && e.x >= 66.67).length,
    tkl: c('tackle'),
    int: c('int'),
    rec: c('rec'),
    aer: c('aer'),
    aerA: c('aer') + c('aerlost'),
    drb: c('dribble'),
    fouls: c('foul'),
    clr: c('clr'),
    saves: c('save'),
  };
}

/**
 * On-ball action counts per third, in our attacking direction.
 * Returns [[us, them] defensive third, [us, them] middle, [us, them] attacking].
 */
export function thirds(m) {
  const z = [[0, 0], [0, 0], [0, 0]];
  m.events.forEach((e) => {
    if (!isOn(e)) return;
    const x = e.team === 'us' ? e.x : 100 - e.x;
    const i = x < 33.34 ? 0 : x < 66.67 ? 1 : 2;
    z[i][e.team === 'us' ? 0 : 1]++;
  });
  return z;
}

export function playerStats(m, pid) {
  const ev = m.events.filter((e) => e.team === 'us' && e.pid === pid);
  const c = (t) => ev.filter((e) => e.type === t).length;
  const shots = ev.filter(isShot);
  const as = m.events.filter((e) => e.team === 'us' && isShot(e) && e.ast === pid);
  return {
    goals: c('goal'),
    assists: as.filter((e) => e.type === 'goal').length,
    xg: sum(shots, xgOf),
    xa: sum(as, xgOf),
    shots: shots.length,
    sot: c('goal') + c('saved'),
    bcMiss: shots.filter((e) => e.big && e.type !== 'goal').length,
    kp: as.length,
    passC: c('pass') + as.length,
    passL: c('passlost'),
    drbW: c('dribble'),
    drbL: c('dribblelost'),
    disp: c('disp'),
    tklW: c('tackle'),
    tklL: c('tacklelost'),
    int: c('int'),
    rec: c('rec'),
    clr: c('clr'),
    aerW: c('aer'),
    aerL: c('aerlost'),
    fouls: c('foul'),
    saves: c('save'),
    touches: ev.filter(isOn).length + as.length,
    actions: ev.length + as.length,
  };
}

export const halfLen = (m) => Number(m.half) || 45;

const isBlank = (v) => v === '' || v == null;

/** Minutes played: explicit override, else lineup on/off, else the full match. */
export function minsOf(m, pid) {
  const v = m.minutes && m.minutes[pid];
  if (!isBlank(v)) return Number(v);
  const l = m.lineup && m.lineup[pid];
  if (l && l.pos) {
    const on = Number(l.on) || 0;
    const off = !isBlank(l.off) ? Number(l.off) : halfLen(m) * 2;
    return Math.max(0, off - on);
  }
  return halfLen(m) * 2;
}

/** Lineup position for this match, falling back to the player's squad position. */
export function posPlayed(m, p) {
  const l = m.lineup && m.lineup[p.id];
  return l && l.pos ? l.pos : p.pos;
}

export function posGroup(m, p) {
  return GROUP[posPlayed(m, p)] || p.pos;
}

/** Squad players who took part: in the lineup, credited with an action, or given minutes. */
export function involved(m, roster) {
  return roster.filter((p) => {
    if (m.lineup && m.lineup[p.id] && m.lineup[p.id].pos) return true;
    const st = playerStats(m, p.id);
    const set = m.minutes && !isBlank(m.minutes[p.id]);
    return st.actions > 0 || (set && Number(m.minutes[p.id]) > 0);
  });
}

export function sortedMatches(matches) {
  return matches.slice().sort((a, b) => (b.date || '').localeCompare(a.date || '') || (b.created || 0) - (a.created || 0));
}

export function chronMatches(matches) {
  return matches.slice().sort((a, b) => (a.date || '').localeCompare(b.date || '') || (a.created || 0) - (b.created || 0));
}
