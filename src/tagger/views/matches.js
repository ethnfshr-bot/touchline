import { FORMS } from '../../engine/actions.js';
import { score, sortedMatches } from '../../engine/stats.js';
import { esc } from '../dom.js';
import { matchList, ui } from '../state.js';

function dataPanel() {
  return `<div class="panel"><h2>Your data</h2>
  <p class="hint" style="margin-top:0">Everything is stored in this browser only. Export a backup regularly, and use export and import to move data between devices or share it with a teammate.</p>
  <div class="row" style="margin-top:.6rem">
    <button class="btn" data-a="export">Export all data (JSON)</button>
    <label class="btn">Import JSON<input type="file" id="importfile" accept="application/json,.json" hidden></label>
    <label class="small muted row" style="gap:.3rem"><input type="checkbox" id="import-replace"> Replace everything instead of merging</label>
  </div></div>`;
}

export function vMatches() {
  const list = sortedMatches(matchList());
  const rows = list
    .map((m) => {
      const [u, t] = score(m);
      return `<div class="match">
    <div class="sc">${u}–${t}</div>
    <div class="info"><div><b>vs ${esc(m.opp || 'Opponent')}</b></div><div class="muted small">${esc(m.date || '')}${m.comp ? ' · ' + esc(m.comp) : ''} · ${m.events.length} events</div></div>
    <div class="row"><button class="btn" data-a="open" data-id="${esc(m.id)}">Tag</button><button class="btn" data-a="openrep" data-id="${esc(m.id)}">Report</button>
    <button class="btn danger" data-a="delmatch" data-id="${esc(m.id)}">${ui.armed === 'm' + m.id ? 'Tap again' : 'Delete'}</button></div></div>`;
    })
    .join('');
  return `<div class="panel"><h2>New match</h2>
  <div class="row">
    <label class="f">Opponent<input type="text" id="nm-opp" placeholder="e.g. Boulder FC"></label>
    <label class="f">Date<input type="date" id="nm-date" value="${new Date().toISOString().slice(0, 10)}"></label>
  </div><div class="row" style="margin-top:.5rem">
    <label class="f">Competition<input type="text" id="nm-comp" placeholder="League, cup, indoor…"></label>
    <label class="f" style="flex:0 1 110px">Half length<input type="number" id="nm-half" value="45" min="10" max="60"></label>
    <label class="f" style="flex:0 1 130px">Formation<select id="nm-form"><option value="">Not set</option>${FORMS.map((f) => `<option>${f}</option>`).join('')}</select></label>
  </div><div class="row" style="margin-top:.5rem">
    <label class="f">Video link (optional): YouTube or Veo<input type="url" id="nm-veo" placeholder="https://youtu.be/… or https://app.veo.co/matches/…"></label>
  </div>
  <p class="hint">Have the video as a file instead? Open it on the Tag screen. It plays from your computer and is never uploaded.</p>
  <div class="row" style="margin-top:.8rem"><button class="btn primary" data-a="newmatch">Create match and start tagging</button></div></div>
  <div class="panel"><h2>Matches</h2>${list.length ? rows : '<div class="empty">No matches yet. Create one above, then tag it while you watch the recording.</div>'}</div>
  ${dataPanel()}`;
}
