import { clamp } from './util.js';
import { involved, minsOf, playerStats, posGroup, score } from './stats.js';

/*
 * Touchline's own FotMob-style rating. FotMob's real model is private, so this is
 * a transparent additive formula: start at BASE and add WEIGHTS[stat] * count.
 * Phase 3 calibrates these weights against real FotMob ratings by regression.
 */
export const BASE = 6.0;
export const MIN_MINUTES = 10;
export const RATING_MIN = 3;
export const RATING_MAX = 10;

export const WEIGHTS = {
  goals: 1.0,
  assists: 0.6,
  xg: 0.4,
  xa: 0.3,
  kp: 0.15,
  sot: 0.1,
  bcMiss: -0.25,
  passC: 0.012,
  passL: -0.03,
  drbW: 0.1,
  drbL: -0.05,
  disp: -0.08,
  tklW: 0.1,
  tklL: -0.05,
  int: 0.1,
  rec: 0.04,
  clr: 0.05,
  aerW: 0.05,
  aerL: -0.03,
  fouls: -0.05,
  saves: 0.2,
};

/** Keepers and defenders who play CLEAN_SHEET_MINUTES+ get a bonus or penalty for goals conceded. */
export const CLEAN_SHEET_MINUTES = 60;
export const CLEAN_SHEET_BONUS = 0.4;
export const CONCEDED_PENALTY = 0.15;
export const CONCEDED_CAP = 4;

/**
 * @param {object} s         playerStats() result
 * @param {string} pos       position group: GK | DEF | MID | FWD
 * @param {number} conceded  goals the team conceded in the match
 * @param {number} mins      minutes played
 * @returns {number|null}    rating, or null if they played under MIN_MINUTES
 */
export function rating(s, pos, conceded, mins) {
  if (!(mins >= MIN_MINUTES)) return null;
  let r = BASE;
  for (const k in WEIGHTS) r += (s[k] || 0) * WEIGHTS[k];
  if ((pos === 'GK' || pos === 'DEF') && mins >= CLEAN_SHEET_MINUTES) {
    r += conceded === 0 ? CLEAN_SHEET_BONUS : -CONCEDED_PENALTY * Math.min(conceded, CONCEDED_CAP);
  }
  return clamp(r, RATING_MIN, RATING_MAX);
}

/** Rating band used for colouring: 'great' 8+, 'good' 7+, 'ok' 6+, else 'bad'. */
export function ratingBand(r) {
  return r >= 8 ? 'great' : r >= 7 ? 'good' : r >= 6 ? 'ok' : 'bad';
}

/** Stats, minutes and rating for every involved player in a match. */
export function matchRatings(m, roster) {
  const conceded = score(m)[1];
  return involved(m, roster).map((p) => {
    const st = playerStats(m, p.id);
    const mn = minsOf(m, p.id);
    return { p, st, mn, r: rating(st, posGroup(m, p), conceded, mn) };
  });
}
