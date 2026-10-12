/*
 * Where on the pitch things happen, for tactical questions like "where do we
 * lose the ball?" and "does our press win it back high up?".
 *
 * The pitch is split into a 3 x 3 grid in our attacking frame (x = 0 our goal
 * line, x = 100 theirs): thirds along the length (defensive, middle,
 * attacking) and channels across (left, centre, right as we attack; y = 0 is
 * the far touchline, which is our left when attacking towards x = 100).
 */
export const WINS = ['tackle', 'int', 'rec'];
export const LOSSES = ['passlost', 'disp', 'dribblelost'];
export const THIRDS = ['defensive', 'middle', 'attacking'];
export const CHANNELS = ['left', 'centre', 'right'];

const third = (x) => (x < 100 / 3 ? 0 : x < 200 / 3 ? 1 : 2);

/** 3x3 counts [third][channel] of our events of the given types across matches. */
export function zoneGrid(matches, types) {
  const g = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const m of matches) {
    for (const e of m.events) {
      if (e.team !== 'us' || e.noloc || !types.includes(e.type)) continue;
      g[third(e.x)][third(e.y)]++;
    }
  }
  return g;
}

export const thirdTotals = (g) => g.map((row) => row[0] + row[1] + row[2]);
export const gridTotal = (g) => thirdTotals(g).reduce((a, b) => a + b, 0);

const MIN_EVENTS = 8;

/** Plain-English observations about where the ball is won and lost. */
export function zoneInsights(wins, losses) {
  const out = [];
  const nl = gridTotal(losses);
  const nw = gridTotal(wins);
  if (nl >= MIN_EVENTS) {
    const [d] = thirdTotals(losses);
    const share = Math.round((d / nl) * 100);
    if (share >= 35) out.push(`${share}% of your turnovers happen in your defensive third. Losing the ball there is the most dangerous place to lose it.`);
    const ch = [0, 1, 2].map((c) => losses[0][c] + losses[1][c] + losses[2][c]);
    const top = ch.indexOf(Math.max(...ch));
    if (ch[top] / nl >= 0.5) out.push(`Half of your turnovers come down the ${CHANNELS[top]} side.`);
  }
  if (nw >= MIN_EVENTS) {
    const [, , a] = thirdTotals(wins);
    const share = Math.round((a / nw) * 100);
    if (share >= 25) out.push(`You win ${share}% of your ball recoveries in the attacking third: your press is winning the ball high up.`);
    else if (share <= 8) out.push(`Only ${share}% of your ball recoveries come in the attacking third: you mostly win it back deep.`);
  }
  return out;
}
