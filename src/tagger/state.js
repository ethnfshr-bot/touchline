/** All persisted data. Replace `store.data` wholesale on load or import. */
export const store = { data: { roster: [], matches: {} } };

/** Transient UI state. Not persisted. */
export const ui = {
  view: 'matches',
  active: null, // match being tagged
  team: 'us',
  pid: null, // selected player chip
  mark: null, // pending pitch location {sx, sy} in SVG units
  mods: { header: false, big: false, pen: false, ast: '' },
  reportId: null,
  focus: null, // player focused in the report
  sp: null, // player selected in the season view
  per90: false,
  armed: null, // key of a delete button awaiting its second tap
  undo: [], // ids of events tagged this session, most recent last: { matchId, id }
  lineOpen: false,
};

/** Most recent event tagged this session in match m that still exists, or null. */
export function undoTarget(m) {
  for (let i = ui.undo.length - 1; i >= 0; i--) {
    const u = ui.undo[i];
    if (u.matchId === m.id && m.events.some((e) => e.id === u.id)) return u.id;
  }
  return null;
}

export const roster = () => store.data.roster;
export const matchList = () => Object.values(store.data.matches);

export const pName = (pid) => {
  const p = store.data.roster.find((x) => x.id === pid);
  return p ? p.name : 'Unassigned';
};
