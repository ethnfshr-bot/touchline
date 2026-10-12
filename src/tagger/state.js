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
  lastId: null,
  lineOpen: false,
};

export const roster = () => store.data.roster;
export const matchList = () => Object.values(store.data.matches);

export const pName = (pid) => {
  const p = store.data.roster.find((x) => x.id === pid);
  return p ? p.name : 'Unassigned';
};
