// Shot positions with known xG under the current hand-tuned model.
export const PEN_SPOT = { x: 89.5238, y: 50 }; // 11 m out, central: 0.2756 xG
export const EDGE_OF_BOX = { x: 84.2857, y: 50 }; // 16.5 m out, central: 0.1202 xG
export const XG_PEN_SPOT = 0.27560121224801043;
export const XG_EDGE_OF_BOX = 0.12024090228356879;

export const roster = [
  { id: 'gk', name: 'Keeper', num: 1, pos: 'GK' },
  { id: 'def', name: 'Defender', num: 4, pos: 'DEF' },
  { id: 'mid', name: 'Midfielder', num: 8, pos: 'MID' },
  { id: 'fwd', name: 'Forward', num: 9, pos: 'FWD' },
  { id: 'sub', name: 'Sub', num: 14, pos: 'MID' },
  { id: 'bench', name: 'Unused', num: 16, pos: 'FWD' },
];

let n = 0;
export const ev = (team, type, extra = {}) => ({ id: 'e' + n++, t: 0, team, type, x: 50, y: 50, ...extra });

/** A 1–1 match. Calling it twice gives identical matches (event ids restart). */
export function makeMatch(over = {}) {
  n = 0;
  return {
    id: 'm1',
    created: 1,
    opp: 'Boulder FC',
    date: '2026-09-06',
    comp: 'League',
    half: 45,
    veo: '',
    formation: '4-4-2',
    minutes: { def: 75, bench: '' },
    lineup: {
      gk: { pos: 'GK', on: '', off: '' },
      mid: { pos: 'AM', on: '', off: 80 },
      sub: { pos: 'CM', on: 60, off: '' },
    },
    events: [
      ev('us', 'pass', { pid: 'mid', t: 100 }),
      ev('us', 'pass', { pid: 'mid', t: 200 }),
      ev('us', 'pass', { pid: 'mid', t: 300 }),
      ev('us', 'passlost', { pid: 'mid', t: 400 }),
      ev('us', 'tackle', { pid: 'def', t: 500 }),
      ev('us', 'int', { pid: 'def', t: 550 }),
      ev('us', 'goal', { pid: 'fwd', ast: 'mid', t: 600, ...PEN_SPOT }),
      ev('us', 'saved', { pid: 'fwd', t: 700, ...EDGE_OF_BOX }),
      ev('us', 'touch', { pid: 'fwd', t: 800, x: 70 }),
      ev('them', 'pass', { t: 2000, x: 70 }),
      ev('them', 'goal', { t: 3000, ...PEN_SPOT }),
    ],
    ...over,
  };
}
