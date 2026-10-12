import { $ } from './dom.js';
import { ui } from './state.js';
import { videoActive } from './video.js';
import { vMatches } from './views/matches.js';
import { vReport } from './views/report.js';
import { vSeason } from './views/season.js';
import { vSquad } from './views/squad.js';
import { vTag } from './views/tag.js';

const VIEWS = { matches: vMatches, tag: vTag, report: vReport, season: vSeason, squad: vSquad };

/** Re-render the current view from state. Every state change calls this. */
export function render() {
  document.querySelectorAll('#nav button').forEach((b) => b.setAttribute('aria-current', b.dataset.v === ui.view ? 'page' : 'false'));
  $('#app').innerHTML = VIEWS[ui.view]();
  // The player sits outside #app so playback survives re-renders; show it only while tagging.
  $('#player').hidden = !(ui.view === 'tag' && videoActive());
}
