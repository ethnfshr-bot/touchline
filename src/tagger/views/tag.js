import { ACT, FORMS, GROUPS, POSP, isShot } from '../../engine/actions.js';
import { halfLen, score } from '../../engine/stats.js';
import { f2 } from '../../engine/util.js';
import { xgOf } from '../../engine/xg.js';
import { clock, fmt, nowSec } from '../clock.js';
import { esc } from '../dom.js';
import { pitchSVG, toScreen } from '../pitch.js';
import { pName, roster, store, ui } from '../state.js';
import { isPaused, videoActive } from '../video.js';

function lineupPanel(m) {
  const lu = m.lineup || {};
  const starters = Object.values(lu).filter((l) => l.pos && (l.on === '' || l.on == null || Number(l.on) === 0)).length;
  const rows = roster()
    .map((p) => {
      const l = lu[p.id] || {};
      const id = esc(p.id);
      return `<tr><td>${esc(p.name)}</td><td><select data-lu="${id}" data-f="pos" style="width:auto"><option value="">Didn't play</option>${POSP.map((x) => `<option ${l.pos === x ? 'selected' : ''}>${x}</option>`).join('')}</select></td>
    <td><input type="number" min="0" max="130" placeholder="0" value="${l.on != null ? esc(l.on) : ''}" data-lu="${id}" data-f="on" aria-label="Minute on"></td><td><input type="number" min="0" max="130" placeholder="${halfLen(m) * 2}" value="${l.off != null ? esc(l.off) : ''}" data-lu="${id}" data-f="off" aria-label="Minute off"></td></tr>`;
    })
    .join('');
  return `<details class="panel" id="lineup" ${ui.lineOpen ? 'open' : ''}><summary style="cursor:pointer"><b style="font-family:var(--head);font-size:1.1rem">Lineup and formation</b> <span class="muted small">${esc(m.formation || 'No formation set')}, ${starters}/11 starters</span></summary>
  <div class="row" style="margin:.7rem 0"><label class="f" style="flex:0 1 160px">Formation<select id="lu-form"><option value="">Not set</option>${FORMS.map((f) => `<option ${m.formation === f ? 'selected' : ''}>${f}</option>`).join('')}</select></label></div>
  ${
    roster().length
      ? `<div class="tw"><table><thead><tr><th>Player</th><th>Position</th><th>On (min)</th><th>Off (min)</th></tr></thead><tbody>${rows}</tbody></table></div>
  <p class="hint">Leave On blank for starters and Off blank if they played to full time. Minutes, ratings by position and on/off splits come from this.</p>`
      : '<p class="hint">Add your squad first.</p>'
  }</details>`;
}

function videoPicker(m) {
  const v = m.video || {};
  const last = v.source === 'file' && v.name && !videoActive() ? `<p class="hint">Last time you used <b>${esc(v.name)}</b>. Load it again to keep tagging in sync.</p>` : '';
  return `<div class="vidrow">
      <label class="btn">Open video file<input type="file" id="videofile" accept="video/*,.mp4,.mov,.m4v,.webm,.mkv" hidden></label>
      <input type="url" id="yt-url" placeholder="or paste a YouTube link" aria-label="YouTube link" value="${v.source === 'youtube' && !videoActive() ? esc('https://youtu.be/' + v.youtubeId) : ''}">
      <button class="btn" data-a="yt-load">Load</button>
    </div>${last}`;
}

function clockPanel(m) {
  if (!videoActive()) {
    return `<div class="clock" style="margin-top:.7rem">
      <input type="text" id="clk" value="${fmt(nowSec())}" aria-label="Match clock (mm:ss)" inputmode="numeric">
      <button class="btn primary" data-a="clk-toggle" id="clk-toggle">${clock.running ? 'Pause' : 'Start'}</button>
      <button class="btn" data-a="clk-add" data-n="-5">−5s</button><button class="btn" data-a="clk-add" data-n="5">+5s</button>
      <button class="btn" data-a="clk-half">2nd half</button>
    </div>
    <p class="hint">Load the match video to tag while it plays, or run the clock alongside it and type the match time. Events are stamped with it.</p>
    ${videoPicker(m)}`;
  }
  const v = m.video || {};
  const marks = [
    v.k1 != null ? `kick-off at ${fmt(v.k1)}` : 'kick-off not marked (assuming the video starts at kick-off)',
    v.k2 != null ? `2nd half at ${fmt(v.k2)}` : '2nd half not marked',
  ].join(' · ');
  return `<div class="clock" style="margin-top:.7rem">
      <input type="text" id="clk" value="${fmt(nowSec())}" aria-label="Match time (mm:ss); type to jump" inputmode="numeric">
      <button class="btn primary" data-a="clk-toggle" id="clk-toggle">${isPaused() ? 'Play' : 'Pause'}</button>
      <button class="btn" data-a="clk-add" data-n="-5">−5s</button><button class="btn" data-a="clk-add" data-n="5">+5s</button>
      <button class="btn" data-a="mark-k1">Mark kick-off</button>
      <button class="btn" data-a="mark-k2">Mark 2nd-half kick-off</button>
      <button class="btn" data-a="video-close">Close video</button>
    </div>
    <p class="hint">Video: ${marks}. Pause on each kick-off and press its button; earlier events re-time automatically.
    Keys: Space play/pause, ← → 5 seconds. Click a minute in the event log to replay it.</p>`;
}

function actionButtons() {
  const dis = ui.mark ? '' : 'disabled';
  return GROUPS.map(([g, gl]) => {
    const btns = Object.entries(ACT)
      .filter(([, a]) => a.g === g)
      .map(([k, a]) => `<button class="act ${g === 'shot' ? 'shot' : ''}" data-a="log" data-t="${k}" ${dis}>${a.l}</button>`)
      .join('');
    const mods =
      g === 'shot'
        ? `<div class="chips" style="width:100%;margin-top:.2rem">
        <button class="chip tog" data-a="mod" data-m="header" aria-pressed="${ui.mods.header}">Header</button>
        <button class="chip tog" data-a="mod" data-m="big" aria-pressed="${ui.mods.big}">Big chance</button>
        <button class="chip tog" data-a="mod" data-m="pen" aria-pressed="${ui.mods.pen}">Penalty</button>
        ${
          ui.team === 'us' && roster().length
            ? `<select id="astsel" aria-label="Assisted by" style="width:auto"><option value="">No assist</option>${roster()
                .map((p) => `<option value="${esc(p.id)}" ${ui.mods.ast === p.id ? 'selected' : ''}>Ast: ${esc(p.name)}</option>`)
                .join('')}</select>`
            : ''
        }
      </div>`
        : '';
    return `<div class="grp"><div class="gl">${gl}</div>${btns}${mods}</div>`;
  }).join('');
}

export function vTag() {
  const m = store.data.matches[ui.active];
  if (!m) {
    return `<div class="panel empty">Choose a match to tag.<div class="row" style="justify-content:center;margin-top:.8rem"><button class="btn primary" data-a="view" data-v="matches">Go to matches</button></div></div>`;
  }
  const [u, t] = score(m);
  const markers = m.events
    .slice(-12)
    .map((e) => {
      const p = toScreen(e.team, e.x, e.y);
      return `<circle cx="${p.sx}" cy="${p.sy}" r="${isShot(e) ? 1.3 : 0.8}" fill="${e.team === 'us' ? 'var(--us)' : 'var(--them)'}" opacity=".7"/>`;
    })
    .join('');
  const mk = ui.mark
    ? `<circle cx="${ui.mark.sx}" cy="${ui.mark.sy}" r="2" fill="none" stroke="var(--gold)" stroke-width=".7"/><circle cx="${ui.mark.sx}" cy="${ui.mark.sy}" r=".6" fill="var(--gold)"/>`
    : '';
  const arrow = `<text x="${ui.team === 'us' ? 94 : 11}" y="66.3" font-size="2.6" fill="var(--chalk)" text-anchor="middle" font-family="Barlow Condensed">${ui.team === 'us' ? 'You attack →' : '← They attack'}</text>`;
  const players = roster()
    .map((p) => `<button class="chip" data-a="pid" data-id="${esc(p.id)}" aria-pressed="${ui.pid === p.id}">${p.num != null && p.num !== '' ? esc(p.num) + ' ' : ''}${esc(p.name)}</button>`)
    .join('');
  const log = m.events
    .slice()
    .reverse()
    .slice(0, 40)
    .map(
      (e) => `<li><span class="dot" style="background:${e.team === 'us' ? 'var(--us)' : 'var(--them)'}"></span>
    ${videoActive() && typeof e.vt === 'number' ? `<button class="linkish" data-a="seek" data-n="${e.vt}" aria-label="Replay in video">${Math.floor(e.t / 60) + 1}'</button>` : `<span>${Math.floor(e.t / 60) + 1}'</span>`}<span>${e.team === 'us' ? esc(pName(e.pid)) : 'Opposition'} · ${ACT[e.type].l}${isShot(e) ? ` <span class="muted">(${f2(xgOf(e))} xG${e.ast ? ', ast ' + esc(pName(e.ast)) : ''})</span>` : ''}</span>
    <button class="x" data-a="delev" data-id="${esc(e.id)}" aria-label="Delete event">×</button></li>`,
    )
    .join('');
  const veo = m.veo && /^https:\/\//.test(m.veo) ? `<a class="btn" href="${esc(m.veo)}" target="_blank" rel="noopener">Open in Veo</a>` : '';
  const playerPicker =
    ui.team === 'us'
      ? roster().length
        ? `<div class="chips" style="margin-bottom:.6rem">${players}</div>`
        : `<p class="hint" style="margin:0 0 .6rem">Add players under Squad to credit actions. Until then, actions log as unassigned.</p>`
      : '';
  return `<div class="panel"><div class="row" style="justify-content:space-between">
    <div><h2 style="margin:0">${u}–${t} vs ${esc(m.opp || 'Opponent')}</h2><div class="muted small">${esc(m.date || '')}${m.comp ? ' · ' + esc(m.comp) : ''}</div></div>${veo}</div>
    ${clockPanel(m)}</div>
  ${lineupPanel(m)}
  <div class="grid2">
  <div>
    <div class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:.6rem">
        <div class="seg"><button class="us" data-a="team" data-v="us" aria-pressed="${ui.team === 'us'}">Us</button><button class="them" data-a="team" data-v="them" aria-pressed="${ui.team === 'them'}">Them</button></div>
        <button class="btn" data-a="undo" ${m.events.length ? '' : 'disabled'}>Undo last</button>
      </div>
      ${playerPicker}
      <div class="pitchwrap">${pitchSVG(markers + arrow + mk, 'tagpitch')}</div>
      <p class="hint">${ui.mark ? 'Now pick what happened.' : 'Tap where the action happened.'}</p>
    </div>
  </div>
  <div>
    <div class="panel acts">${actionButtons()}</div>
    <div class="panel"><h3>Event log</h3>${m.events.length ? `<ul class="log">${log}</ul>` : '<p class="muted small" style="margin:0">Nothing tagged yet.</p>'}</div>
  </div></div>`;
}
