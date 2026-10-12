import { POS } from '../../engine/actions.js';
import { esc } from '../dom.js';
import { roster, ui } from '../state.js';

export function vSquad() {
  const list = roster();
  const rows = list
    .map(
      (p) =>
        `<tr><td>${esc(p.name)}</td><td>${p.num != null && p.num !== '' ? esc(p.num) : '–'}</td><td>${esc(p.pos)}</td><td><button class="btn danger" data-a="delplayer" data-id="${esc(p.id)}">${ui.armed === 'p' + p.id ? 'Tap again' : 'Remove'}</button></td></tr>`,
    )
    .join('');
  return `<div class="panel"><h2>Add a player</h2><div class="row">
    <label class="f">Name<input type="text" id="np-name" placeholder="Player name"></label>
    <label class="f" style="flex:0 1 80px">Number<input type="number" id="np-num" min="0" max="99"></label>
    <label class="f" style="flex:0 1 110px">Position<select id="np-pos">${POS.map((p) => `<option>${p}</option>`).join('')}</select></label>
  </div><div class="row" style="margin-top:.8rem"><button class="btn primary" data-a="addplayer">Add player</button></div>
  <p class="hint">Position matters for ratings: keepers and defenders gain or lose points for goals conceded.</p></div>
  <div class="panel"><h2>Squad</h2>${
    list.length
      ? `<div class="tw"><table><thead><tr><th>Player</th><th>No.</th><th>Pos</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '<div class="empty">Add your team so you can credit each action to a player.</div>'
  }</div>`;
}
