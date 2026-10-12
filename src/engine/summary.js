import { matchRatings } from './rating.js';
import { score, teamStats } from './stats.js';
import { f1 } from './util.js';

/*
 * Plain-English match summary: a few sentences a coach can read in ten
 * seconds. Rules are deliberately simple and conservative; every sentence is
 * traceable to a number shown elsewhere in the report.
 */
export const XG_GAP = 0.4; // smaller xG gaps are too close to call
export const FINISHING_GAP = 1.0;

const pct = (a, b) => (a + b ? Math.round((a / (a + b)) * 100) : null);

/**
 * @param {object} m       match
 * @param {object[]} roster
 * @param {string} opp     opposition name for the sentences
 * @returns {string[]}     sentences, empty if there's too little tagged
 */
export function matchSummary(m, roster, opp = 'the opposition') {
  const A = teamStats(m, 'us');
  const B = teamStats(m, 'them');
  const [u, t] = score(m);
  if (A.shots + B.shots === 0 && u + t === 0) return [];
  const out = [];
  const result = u > t ? `You won ${u}–${t}` : u < t ? `You lost ${u}–${t}` : `It finished ${u}–${t}`;

  const gap = A.xg - B.xg;
  const xgText = `${f1(A.xg)} xG to ${f1(B.xg)}`;
  if (Math.abs(gap) < XG_GAP) {
    out.push(`${result}. Chances were even (${xgText}).`);
  } else if (gap > 0) {
    const fair = u > t ? 'a fair reflection' : u === t ? 'harsh on you' : "not a fair reflection of the play";
    out.push(`${result}, and you created the better chances (${xgText}), so the result was ${fair}.`);
  } else {
    const fair = u < t ? 'a fair reflection' : u === t ? 'a good point' : 'better than the chances suggest';
    out.push(`${result}; ${opp} created the better chances (${f1(B.xg)} xG to ${f1(A.xg)}), so the result was ${fair}.`);
  }

  if (u - A.xg >= FINISHING_GAP) out.push(`Clinical finishing: ${u} goals from chances worth ${f1(A.xg)}.`);
  else if (A.xg - u >= FINISHING_GAP) out.push(`Wasteful in front of goal: ${u} from chances worth ${f1(A.xg)}.`);
  if (A.bigMiss >= 2) out.push(`You missed ${A.bigMiss} big chances.`);
  if (t - B.xg >= FINISHING_GAP) out.push(`${cap(opp)} scored more than their chances deserved (${t} from ${f1(B.xg)} xG).`);

  const poss = pct(A.onball, B.onball);
  const tilt = pct(A.ft, B.ft);
  if (poss != null && A.onball >= 20 && B.onball >= 20) {
    out.push(`You had ${poss}% of the ball${tilt != null ? ` and ${tilt}% of the play in the final third` : ''}.`);
  }

  const rated = matchRatings(m, roster).filter((x) => x.r != null);
  if (rated.length >= 3) {
    const best = rated.reduce((a, b) => (b.r > a.r ? b : a));
    out.push(`Player of the match: ${best.p.name} (${f1(best.r)}).`);
  }
  return out;
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
