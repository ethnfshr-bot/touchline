import { ACT, isShot } from '../engine/actions.js';
import { seasonRows } from '../engine/season.js';
import { halfLen } from '../engine/stats.js';
import { clamp, f2 } from '../engine/util.js';
import { parseYouTubeId } from '../engine/videosource.js';
import { retimeEvents } from '../engine/videotime.js';
import { xgOf } from '../engine/xg.js';
import { AutoTagError, mergeAutoTags, parseAutoTags } from '../storage/autotags.js';
import { ImportError, mergeData, parseImport, toExport } from '../storage/io.js';
import { clock, fmt, nowSec, parseClock, setClock } from './clock.js';
import { $, downloadFile, mkid, toast } from './dom.js';
import { saveAll, saveMatch, saveRoster } from './persist.js';
import { svgPoint, toFrame } from './pitch.js';
import { render } from './render.js';
import { matchList, roster, store, ui, undoTarget } from './state.js';
import { isPaused, loadFile, loadYouTube, seekMatch, seekVideo, setPlayerHooks, togglePlay, unloadVideo, videoActive, videoTime } from './video.js';

const REPLAY_LEAD_IN = 3; // seconds of build-up shown when replaying an event

/** Load the match's saved YouTube video, if it has one. */
function autoloadVideo(m) {
  if (m && m.video && m.video.source === 'youtube' && m.video.youtubeId) {
    loadYouTube(m.video.youtubeId, m).then(render);
  }
}

function markKickoff(m, key) {
  const t = Math.round(videoTime() * 10) / 10;
  const v = { ...m.video, [key]: t };
  if (v.k1 != null && v.k2 != null && v.k2 <= v.k1) {
    toast('The 2nd-half kick-off must come after the first.', 3000);
    return;
  }
  m.video = v;
  retimeEvents(m.events, m.video, halfLen(m));
  saveMatch(m.id);
  render();
  toast(`${key === 'k1' ? 'Kick-off' : '2nd-half kick-off'} marked at ${fmt(t)} in the video`);
}

function logEvent(type) {
  const m = store.data.matches[ui.active];
  if (!m || !ui.mark) return;
  const f = toFrame(ui.team, ui.mark.sx, ui.mark.sy);
  const e = { id: mkid(), t: Math.floor(nowSec()), team: ui.team, type, x: Math.round(f.x * 10) / 10, y: Math.round(f.y * 10) / 10 };
  if (videoActive()) e.vt = Math.round(videoTime() * 10) / 10;
  if (ui.team === 'us' && ui.pid) e.pid = ui.pid;
  if (ACT[type].shot) {
    if (ui.mods.header) e.header = 1;
    if (ui.mods.big) e.big = 1;
    if (ui.mods.pen) e.pen = 1;
    if (ui.team === 'us' && ui.mods.ast && ui.mods.ast !== ui.pid) e.ast = ui.mods.ast;
    ui.mods = { header: false, big: false, pen: false, ast: '' };
  }
  ui.undo.push({ matchId: m.id, id: e.id });
  m.events.push(e);
  m.events.sort((a, b) => a.t - b.t);
  ui.mark = null;
  saveMatch(m.id);
  render();
  toast(`${ACT[type].l}${isShot(e) ? ' · ' + f2(xgOf(e)) + ' xG' : ''}`);
}

function csvEsc(v) {
  v = String(v);
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}

function exportCSV() {
  const head = ['Player', 'Position', 'Avg rating', 'Apps', 'Minutes', 'Goals', 'Assists', 'xG', 'xA', 'Shots', 'Shots on target', 'Key passes', 'Passes completed', 'Passes attempted', 'Dribbles won', 'Tackles won', 'Interceptions', 'Recoveries'];
  const lines = [head.join(',')].concat(
    seasonRows(matchList(), roster()).map(({ p, a }) =>
      [p.name, p.pos, a.rating != null ? f2(a.rating) : '', a.apps, a.mins, a.goals, a.assists, f2(a.xg), f2(a.xa), a.shots, a.sot, a.kp, a.passC, a.passA, a.drbW, a.tklW, a.int, a.rec].map(csvEsc).join(','),
    ),
  );
  downloadFile('touchline-season.csv', lines.join('\n'), 'text/csv');
  toast('Exported');
}

function exportJSON() {
  const stamp = new Date().toISOString().slice(0, 10);
  downloadFile(`touchline-backup-${stamp}.json`, JSON.stringify(toExport(store.data), null, 2), 'application/json');
  toast('Backup downloaded');
}

async function importJSON(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  const replace = $('#import-replace') && $('#import-replace').checked;
  try {
    const incoming = parseImport(await file.text());
    const n = Object.keys(incoming.matches).length;
    if (replace && !confirm(`Replace ALL your data with ${n} matches and ${incoming.roster.length} players from this file? This can't be undone.`)) return;
    store.data = replace ? incoming : mergeData(store.data, incoming);
    await saveAll();
    unloadVideo();
    ui.active = null;
    ui.reportId = null;
    render();
    toast(`Imported ${n} matches and ${incoming.roster.length} players`);
  } catch (e) {
    toast(e instanceof ImportError ? e.message : "Couldn't import that file.");
    if (!(e instanceof ImportError)) console.error(e);
  }
}

async function importAutoTags(input) {
  const file = input.files && input.files[0];
  input.value = '';
  const m = store.data.matches[ui.active];
  if (!file || !m) return;
  try {
    const auto = parseAutoTags(await file.text());
    const merged = mergeAutoTags(m, auto, mkid);
    store.data.matches[m.id] = merged;
    saveMatch(m.id);
    render();
    toast(`Added ${merged.autoInfo.count} automatic tags`, 3000);
  } catch (e) {
    toast(e instanceof AutoTagError ? e.message : "Couldn't read that file.", 5000);
    if (!(e instanceof AutoTagError)) console.error(e);
  }
}

/** Two-tap confirm for destructive buttons. */
function arm(key, fn) {
  if (ui.armed === key) {
    ui.armed = null;
    fn();
  } else {
    ui.armed = key;
    setTimeout(() => {
      if (ui.armed === key) {
        ui.armed = null;
        render();
      }
    }, 3000);
  }
  render();
}

function goTo(view) {
  ui.view = view;
  render();
  window.scrollTo(0, 0);
}

function onClick(evt) {
  const b = evt.target.closest('[data-a]');
  if (!b) {
    const svg = evt.target.closest('#tagpitch');
    if (svg) {
      ui.mark = svgPoint(svg, evt);
      render();
    }
    return;
  }
  const a = b.dataset.a;
  const id = b.dataset.id;
  const m = store.data.matches[ui.active];
  switch (a) {
    case 'view':
      if (b.dataset.v !== 'tag' && videoActive() && !isPaused()) togglePlay();
      ui.mark = null;
      goTo(b.dataset.v);
      break;
    case 'newmatch': {
      const opp = $('#nm-opp').value.trim();
      const link = $('#nm-veo').value.trim();
      const youtubeId = parseYouTubeId(link);
      if (!opp) {
        toast("Add the opponent's name first");
        $('#nm-opp').focus();
        return;
      }
      if (link && !youtubeId && !/^https:\/\//.test(link)) {
        toast('Video link should start with https://');
        return;
      }
      const nm = {
        id: mkid(), created: Date.now(), opp, date: $('#nm-date').value, comp: $('#nm-comp').value.trim(),
        half: clamp(Number($('#nm-half').value) || 45, 10, 60), veo: youtubeId ? '' : link, formation: $('#nm-form').value,
        events: [], minutes: {}, lineup: {},
      };
      if (youtubeId) nm.video = { source: 'youtube', youtubeId };
      store.data.matches[nm.id] = nm;
      saveMatch(nm.id);
      unloadVideo();
      ui.active = nm.id;
      clock.running = false;
      setClock(0);
      goTo('tag');
      autoloadVideo(nm);
      break;
    }
    case 'open': {
      const om = store.data.matches[id];
      const reopen = ui.active === id && videoActive();
      if (!reopen) unloadVideo();
      ui.active = id;
      ui.mark = null;
      clock.running = false;
      setClock(om.events.length ? om.events[om.events.length - 1].t : 0);
      goTo('tag');
      if (!reopen) autoloadVideo(om);
      break;
    }
    case 'openrep':
      ui.reportId = id;
      goTo('report');
      break;
    case 'delmatch':
      arm('m' + id, () => {
        delete store.data.matches[id];
        if (ui.active === id) {
          unloadVideo();
          ui.active = null;
        }
        saveMatch(id);
        toast('Match deleted');
      });
      break;
    case 'addplayer': {
      const name = $('#np-name').value.trim();
      if (!name) {
        toast('Add a name first');
        return;
      }
      store.data.roster.push({ id: mkid(), name, num: $('#np-num').value, pos: $('#np-pos').value });
      saveRoster();
      render();
      $('#np-name').focus();
      break;
    }
    case 'delplayer':
      arm('p' + id, () => {
        store.data.roster = store.data.roster.filter((p) => p.id !== id);
        if (ui.pid === id) ui.pid = null;
        saveRoster();
      });
      break;
    case 'team':
      ui.team = b.dataset.v;
      ui.mark = null;
      render();
      break;
    case 'pid':
      ui.pid = ui.pid === id ? null : id;
      render();
      break;
    case 'mod':
      ui.mods[b.dataset.m] = !ui.mods[b.dataset.m];
      render();
      break;
    case 'log':
      logEvent(b.dataset.t);
      break;
    case 'undo': {
      if (!m) return;
      const target = undoTarget(m);
      if (!target) {
        toast('Nothing to undo. Use × in the event log to delete an older event.', 3000);
        return;
      }
      m.events = m.events.filter((e) => e.id !== target);
      ui.undo = ui.undo.filter((u) => u.id !== target);
      saveMatch(m.id);
      render();
      toast('Removed last event');
      break;
    }
    case 'delev':
      if (!m) return;
      m.events = m.events.filter((e) => e.id !== id);
      saveMatch(m.id);
      render();
      break;
    case 'clk-toggle':
      if (videoActive()) {
        togglePlay();
        return;
      }
      if (clock.running) {
        setClock(nowSec());
        clock.running = false;
      } else {
        clock.at = Date.now();
        clock.running = true;
      }
      render();
      break;
    case 'clk-add':
      if (videoActive()) seekVideo(videoTime() + Number(b.dataset.n));
      else setClock(nowSec() + Number(b.dataset.n));
      render();
      break;
    case 'yt-load': {
      if (!m) return;
      const yid = parseYouTubeId($('#yt-url').value);
      if (!yid) {
        toast("That doesn't look like a YouTube video link.", 3000);
        return;
      }
      loadYouTube(yid, m).then(() => {
        saveMatch(m.id);
        render();
      });
      break;
    }
    case 'mark-k1':
    case 'mark-k2':
      if (m && videoActive()) markKickoff(m, a === 'mark-k1' ? 'k1' : 'k2');
      break;
    case 'video-close':
      unloadVideo();
      render();
      break;
    case 'seek':
      seekVideo(Number(b.dataset.n) - REPLAY_LEAD_IN);
      break;
    case 'clk-half':
      if (videoActive()) return;
      clock.running = false;
      setClock(halfLen(m || {}) * 60);
      render();
      toast('Clock set to start of 2nd half');
      break;
    case 'focus':
      ui.focus = id;
      render();
      break;
    case 'p90':
      ui.per90 = b.dataset.v === '1';
      render();
      break;
    case 'csv':
      exportCSV();
      break;
    case 'export':
      exportJSON();
      break;
  }
}

function onChange(evt) {
  const t = evt.target;
  if (t.id === 'clk') {
    const s = parseClock(t.value);
    if (s == null) {
      toast('Use mm:ss, like 23:40');
      t.value = fmt(nowSec());
      return;
    }
    if (videoActive()) seekMatch(s, store.data.matches[ui.active]);
    else setClock(s);
    return;
  }
  if (t.id === 'importfile') return importJSON(t);
  if (t.id === 'autofile') return importAutoTags(t);
  if (t.id === 'videofile') {
    const file = t.files && t.files[0];
    const m = store.data.matches[ui.active];
    if (!file || !m) return;
    loadFile(file, m);
    saveMatch(m.id);
    render();
    return;
  }
  if (t.id === 'astsel') {
    ui.mods.ast = t.value;
    return;
  }
  if (t.id === 'spsel') {
    ui.sp = t.value;
    render();
    return;
  }
  if (t.id === 'repsel') {
    ui.reportId = t.value;
    ui.focus = null;
    render();
    return;
  }
  if (t.id === 'lu-form') {
    const m = store.data.matches[ui.active];
    if (!m) return;
    m.formation = t.value;
    saveMatch(m.id);
    render();
    return;
  }
  if (t.dataset && t.dataset.lu) {
    const m = store.data.matches[ui.active];
    if (!m) return;
    m.lineup = m.lineup || {};
    const k = t.dataset.lu;
    const f = t.dataset.f;
    const o = m.lineup[k] || (m.lineup[k] = { pos: '', on: '', off: '' });
    o[f] = f === 'pos' ? t.value : t.value === '' ? '' : clamp(Number(t.value) || 0, 0, 130);
    if (!o.pos && o.on === '' && o.off === '') delete m.lineup[k];
    saveMatch(m.id);
    render();
    return;
  }
  if (t.dataset && t.dataset.mins) {
    const m = store.data.matches[ui.reportId];
    if (!m) return;
    m.minutes = m.minutes || {};
    m.minutes[t.dataset.mins] = clamp(Number(t.value) || 0, 0, 130);
    saveMatch(m.id);
    render();
  }
}

/** Video shortcuts on the Tag screen, unless the user is typing or the player itself has focus. */
function onKey(e) {
  if (ui.view !== 'tag' || !videoActive()) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'VIDEO' || e.target.isContentEditable) return;
  if (e.key === ' ') {
    e.preventDefault();
    togglePlay();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault();
    seekVideo(videoTime() + (e.key === 'ArrowLeft' ? -5 : 5));
  }
}

export function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener(
    'toggle',
    (e) => {
      if (e.target && e.target.id === 'lineup') ui.lineOpen = e.target.open;
    },
    true,
  );
  document.addEventListener('keydown', onKey);
  setPlayerHooks({
    state: () => {
      const btn = $('#clk-toggle');
      if (btn && videoActive()) btn.textContent = isPaused() ? 'Play' : 'Pause';
    },
    error: (msg) => {
      unloadVideo();
      render();
      toast(msg, 6000);
    },
  });
  // Keep the visible clock ticking without re-rendering the whole view.
  setInterval(() => {
    if (ui.view !== 'tag') return;
    const el = $('#clk');
    if (el && document.activeElement !== el) el.value = fmt(nowSec());
  }, 250);
}
