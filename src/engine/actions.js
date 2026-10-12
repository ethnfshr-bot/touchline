/**
 * Event vocabulary. Each key is stored as `event.type`.
 *   l    label shown in the UI
 *   g    button group: 'shot' | 'ball' | 'def'
 *   on   counts as an on-the-ball action (possession, touches, field tilt)
 *   shot counts as a shot (xG, shot map)
 */
export const ACT = {
  goal: { l: 'Goal', g: 'shot', on: 1, shot: 1 },
  saved: { l: 'Saved', g: 'shot', on: 1, shot: 1 },
  off: { l: 'Off target', g: 'shot', on: 1, shot: 1 },
  blocked: { l: 'Blocked', g: 'shot', on: 1, shot: 1 },
  pass: { l: 'Pass', g: 'ball', on: 1 },
  passlost: { l: 'Pass lost', g: 'ball', on: 1 },
  touch: { l: 'Touch', g: 'ball', on: 1 },
  dribble: { l: 'Dribble won', g: 'ball', on: 1 },
  dribblelost: { l: 'Dribble lost', g: 'ball', on: 1 },
  disp: { l: 'Lost ball', g: 'ball', on: 1 },
  tackle: { l: 'Tackle won', g: 'def' },
  tacklelost: { l: 'Tackle lost', g: 'def' },
  int: { l: 'Interception', g: 'def' },
  rec: { l: 'Recovery', g: 'def' },
  clr: { l: 'Clearance', g: 'def' },
  aer: { l: 'Aerial won', g: 'def' },
  aerlost: { l: 'Aerial lost', g: 'def' },
  foul: { l: 'Foul', g: 'def' },
  save: { l: 'Save (GK)', g: 'def' },
};

export const GROUPS = [['shot', 'Shot'], ['ball', 'On the ball'], ['def', 'Defending']];

/** Squad position groups (used for ratings). */
export const POS = ['GK', 'DEF', 'MID', 'FWD'];

/** Specific positions a player can be named at in a match lineup. */
export const POSP = ['GK', 'RB', 'CB', 'LB', 'RWB', 'LWB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'];

/** Lineup position -> position group. */
export const GROUP = {
  GK: 'GK', RB: 'DEF', CB: 'DEF', LB: 'DEF', RWB: 'DEF', LWB: 'DEF',
  DM: 'MID', CM: 'MID', AM: 'MID', RM: 'MID', LM: 'MID',
  RW: 'FWD', LW: 'FWD', ST: 'FWD',
};

export const FORMS = ['4-4-2', '4-3-3', '4-2-3-1', '3-5-2', '3-4-3', '5-3-2', '4-1-4-1', '4-4-1-1', 'Other'];

export const isShot = (e) => !!(ACT[e.type] && ACT[e.type].shot);
export const isOn = (e) => !!(ACT[e.type] && ACT[e.type].on);
