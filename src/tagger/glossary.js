import { esc } from './dom.js';

/*
 * Plain-English explanations of every stat, for coaches and players.
 * Each entry: what it is, and why it matters. Keep them short and jargon-free.
 */
export const GLOSSARY = {
  xg: ['Expected goals (xG)', "How many goals a team's chances were worth, based on where each shot was taken from. A shot from the penalty spot is worth about 0.28; a long-range effort about 0.03.", "It shows who created the better chances, which predicts future results better than the score does. Luck evens out; chance quality doesn't."],
  xa: ['Expected assists (xA)', 'The xG of the shots a player set up with their final pass.', 'Rewards creative passing even when the striker misses.'],
  gxg: ['Goals minus xG (G−xG)', 'Goals scored minus the xG of the chances.', 'Above zero: finishing better than the chances suggest (or a lucky spell). Below zero: wasteful, or unlucky. Over a single match it is mostly noise.'],
  sot: ['Shots on target', 'Shots that would have gone in without the keeper: goals plus saves.', "Separates genuine attempts from hopeful ones."],
  big: ['Big chance', 'A chance a player would normally be expected to score, such as a one-on-one or a tap-in. You flag these when tagging.', 'Missing big chances is the clearest sign of poor finishing.'],
  poss: ['Possession', "Each team's share of on-the-ball actions you tagged (passes, touches, dribbles, shots).", "An estimate: it counts actions, not seconds on the ball. Tag both teams' actions or it reads 100%."],
  tilt: ['Field tilt', "Each team's share of on-the-ball actions in the attacking third.", 'Shows who pinned the other back. A team can have less possession but more tilt.'],
  ft: ['Final-third touches', 'On-the-ball actions in the attacking third of the pitch.', 'A simple measure of how often a team got into dangerous areas.'],
  kp: ['Key passes', 'Passes that led directly to a shot.', 'Identifies the players who create chances.'],
  thirds: ['Possession by thirds', 'Where on the pitch each team had the ball: defensive, middle and attacking thirds.', 'Shows whether you build from the back, bypass midfield, or spend the game defending.'],
  race: ['xG race', 'Running total of each team\'s xG through the match. Big dots are goals.', 'Shows which spells of the match each team was on top, not just the final score.'],
  rating: ['Player rating', "A 0–10 score that starts at 6.0 and goes up or down for each action you tag (goals, passes, tackles, mistakes). Keepers and defenders gain or lose points for goals conceded.", "Only as good as the tagging: a player whose actions aren't tagged stays near 6.0. Compare players within your own team, not with professional ratings."],
  p90: ['Per 90', 'A total divided by minutes played, times 90: what the player would produce over a full match.', 'Fair comparison between starters and substitutes.'],
  form: ['Form (last 5)', 'Average rating over the player\'s last five matches.', 'Spots players coming into or out of form.'],
  onoff: ['On/off splits', "Team xG for and against per 90 minutes while the player was on the pitch, compared with while they weren't.", "Shows a player's effect on the whole team, including work that never appears in individual stats. Needs plenty of matches to be reliable."],
  zones: ['Where we win and lose the ball', 'The pitch split into nine zones (three thirds, three channels), counting where your tackles, interceptions and recoveries happened, and where you gave the ball away.', 'Turnovers near your own goal are the most dangerous; regains high up the pitch show a press that works. Patterns across a season are far more reliable than one match.'],
  height: ['Team height', "How far up the pitch the team's outfield players are on average, measured from their own goal line.", 'A high number means playing further forward. Compare in and out of possession to see how far the team drops back when defending.'],
  width: ['Width', 'How spread out the outfield players are across the pitch (ignoring the most extreme player on each side).', 'Wide in possession stretches the opposition; narrow out of possession protects the middle.'],
  depth: ['Depth', 'Distance from the deepest to the most advanced outfield players (ignoring the extremes).', "Large depth out of possession means gaps between the lines for the opposition to play through."],
  area: ['Compactness (area)', 'The area of pitch the outfield players cover, in square metres. Smaller means more compact.', 'Compact teams are harder to play through. Watch whether it grows late in matches as players tire.'],
  line: ['Defensive line', 'How far the deepest outfield player is from their own goal line.', 'A high line squeezes the pitch but leaves space behind; a deep line invites pressure.'],
  territory: ['Territory', 'Share of the time the ball was in each third, from your point of view.', 'Shows where the match was played, measured from the video rather than from memory.'],
  coverage: ['Coverage', "Share of the match where enough of a team's players were on camera to measure its shape.", 'A follow-cam shows only part of the pitch. Low coverage means the shape numbers are based on less of the match; panorama footage gives the most complete picture.'],
  formation: ['By formation', 'Results and xG per match for each formation you set.', 'Tests whether a system actually works for your team, rather than relying on gut feeling.'],
};

/** A collapsible "What do these numbers mean?" panel for the given glossary keys. */
export function glossaryPanel(keys, title = 'What do these numbers mean?') {
  const items = keys
    .map((k) => GLOSSARY[k])
    .filter(Boolean)
    .map(([term, what, why]) => `<dt>${esc(term)}</dt><dd>${esc(what)} <span class="muted">${esc(why)}</span></dd>`)
    .join('');
  return `<details class="panel glossary"><summary>${esc(title)}</summary><dl>${items}</dl></details>`;
}

/** Tooltip text for a stat label (desktop hover; the glossary panel covers touch screens). */
export const tip = (k) => (GLOSSARY[k] ? `title="${esc(GLOSSARY[k][1])}"` : '');
