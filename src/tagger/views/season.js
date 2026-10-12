import { chronMatches, score } from '../../engine/stats.js';
import { formationTable, onOffSplits, playerLog, positionSplits, seasonRows, teamSeason } from '../../engine/season.js';
import { avgOf, f1, f2 } from '../../engine/util.js';
import { barChart, lineChart, rateBadge } from '../charts.js';
import { esc } from '../dom.js';
import { glossaryPanel } from '../glossary.js';
import { zonesPanel } from './zones.js';
import { matchList, roster, ui } from '../state.js';

const signed = (v, fmt) => (v >= 0 ? '+' : '') + fmt(v);
const statlist = (pairs) => `<div class="statlist">${pairs.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('')}</div>`;

function shortLab(m) {
  if (m.date && /^\d{4}-\d{2}-\d{2}$/.test(m.date)) return m.date.slice(8, 10) + '/' + m.date.slice(5, 7);
  return (m.opp || '').slice(0, 6);
}

function formTable(ms) {
  const rows = formationTable(ms);
  if (rows.length === 1 && rows[0].formation === 'Not set') return '<p class="hint">Set the formation in each match lineup to compare systems.</p>';
  return `<div class="muted small" style="margin:.9rem 0 .3rem">By formation</div><div class="tw"><table><thead><tr><th>Formation</th><th>Matches</th><th>W-D-L</th><th>xG for /match</th><th>xG against /match</th><th>xG diff /match</th></tr></thead><tbody>${rows
    .map((o) => `<tr><td>${esc(o.formation)}</td><td>${o.n}</td><td>${o.w}-${o.d}-${o.l}</td><td>${f2(o.xf / o.n)}</td><td>${f2(o.xa / o.n)}</td><td>${signed((o.xf - o.xa) / o.n, f2)}</td></tr>`)
    .join('')}</tbody></table></div>`;
}

function playerSplits(p, ms, log) {
  const posRows = positionSplits(p, log)
    .map((o) => `<tr><td>${esc(o.pos)}</td><td>${o.n}</td><td>${o.mins}</td><td>${rateBadge(o.rating)}</td><td>${o.mins ? f2((o.ga / o.mins) * 90) : '–'}</td><td>${o.mins ? f2((o.xg / o.mins) * 90) : '–'}</td></tr>`)
    .join('');
  const s = onOffSplits(p, ms, roster());
  const p90 = (v, mm) => (mm ? f2((v / mm) * 90) : '–');
  const dif = (f, a, mm) => (mm ? signed(((f - a) / mm) * 90, f2) : '–');
  const onoff =
    s.offM >= 45
      ? `<table><thead><tr><th></th><th>Min</th><th>xG for /90</th><th>xG against /90</th><th>xG diff /90</th></tr></thead><tbody>
    <tr><td>On pitch</td><td>${Math.round(s.onM)}</td><td>${p90(s.onF, s.onM)}</td><td>${p90(s.onA, s.onM)}</td><td>${dif(s.onF, s.onA, s.onM)}</td></tr>
    <tr><td>Off pitch</td><td>${Math.round(s.offM)}</td><td>${p90(s.offF, s.offM)}</td><td>${p90(s.offA, s.offM)}</td><td>${dif(s.offF, s.offA, s.offM)}</td></tr></tbody></table>`
      : '<p class="hint">On/off splits appear once there are matches where this player was off the pitch (subbed, benched or absent).</p>';
  return `<div class="grid2" style="margin-top:.9rem"><div><div class="muted small" style="margin-bottom:.3rem">By position played</div><div class="tw"><table><thead><tr><th>Position</th><th>Apps</th><th>Min</th><th>Avg rating</th><th>G+A /90</th><th>xG /90</th></tr></thead><tbody>${posRows}</tbody></table></div></div>
  <div><div class="muted small" style="margin-bottom:.3rem">Team with and without them</div><div class="tw">${onoff}</div></div></div>`;
}

function teamPanel(ms) {
  const t = teamSeason(ms);
  return `<div class="panel"><h3>Team season</h3>${statlist([
    ['Record (W-D-L)', `${t.w}-${t.d}-${t.l}`], ['Points', t.points], ['Goals for', t.gf], ['Goals against', t.ga],
    ['xG for', f1(t.xf)], ['xG against', f1(t.xa)], ['Goals vs xG', signed(t.gf - t.xf, f1)], ['xG difference', signed(t.xf - t.xa, f1)],
  ])}
    <div class="muted small" style="margin:.9rem 0 .3rem">xG for and against, match by match</div>${barChart(t.pairs, ms.map(shortLab), 'xG for and against by match')}
    <div class="legend"><span><i class="dot" style="background:var(--us)"></i>xG for</span><span><i class="dot" style="background:var(--them)"></i>xG against</span></div>${formTable(ms)}</div>`;
}

function playerPanel(rows, ms) {
  if (!rows.find((r) => r.p.id === ui.sp)) ui.sp = rows[0].p.id;
  const p = roster().find((x) => x.id === ui.sp);
  const log = playerLog(p, ms, roster());
  const rs = log.map((x) => x.r).filter((v) => v != null);
  const avg = avgOf(rs);
  const form = avgOf(rs.slice(-5));
  let cg = 0, cx = 0;
  const cG = [], cX = [];
  log.forEach((x) => {
    cg += x.st.goals;
    cx += x.st.xg;
    cG.push(cg);
    cX.push(cx);
  });
  const mins = log.reduce((a, x) => a + x.mn, 0);
  const gaN = log.reduce((a, x) => a + x.st.goals + x.st.assists, 0);
  const labels = log.map((x) => shortLab(x.m));
  const sel = `<select id="spsel" aria-label="Player" style="width:auto">${rows.map((r) => `<option value="${esc(r.p.id)}" ${r.p.id === p.id ? 'selected' : ''}>${esc(r.p.name)}</option>`).join('')}</select>`;
  const matchRows = log
    .slice()
    .reverse()
    .map((x) => {
      const [u, t] = score(x.m);
      return `<tr><td>${esc(x.m.date || '')} vs ${esc(x.m.opp || '')} <span class="muted small">${u}–${t}</span></td><td>${rateBadge(x.r)}</td><td>${x.mn}</td><td>${x.st.goals}</td><td>${x.st.assists}</td><td>${f2(x.st.xg)}</td><td>${f2(x.st.xa)}</td><td>${x.st.shots}</td><td>${x.st.kp}</td><td>${x.st.passC}/${x.st.passC + x.st.passL}</td><td>${x.st.tklW}</td></tr>`;
    })
    .join('');
  return `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">Player season</h3>${sel}</div>
    ${statlist([
      ['Apps', log.length], ['Minutes', mins], ['Avg rating', avg != null ? f2(avg) : '–'], ['Form (last 5)', form != null ? f2(form) : '–'],
      ['Goals', cg], ['xG', f2(cx)], ['Goals vs xG', signed(cg - cx, f2)], ['G+A per 90', mins ? f2((gaN / mins) * 90) : '–'],
    ])}
    <div class="grid2" style="margin-top:.9rem">
      <div><div class="muted small" style="margin-bottom:.3rem">Rating by match</div>${lineChart([{ vals: log.map((x) => x.r), color: 'var(--gold)' }, { vals: log.map(() => avg), color: 'var(--muted)', dash: 1, dots: false }], labels, { min: 3, max: 10, step: 1, label: 'Rating by match' })}
        <div class="legend"><span><i class="dot" style="background:var(--gold)"></i>Match rating</span><span>Dashed: season average</span></div></div>
      <div><div class="muted small" style="margin-bottom:.3rem">Goals vs xG, cumulative</div>${lineChart([{ vals: cX, color: 'var(--muted)', dash: 1 }, { vals: cG, color: 'var(--us)' }], labels, { label: 'Cumulative goals versus xG' })}
        <div class="legend"><span><i class="dot" style="background:var(--us)"></i>Goals</span><span>Dashed: xG</span></div></div>
    </div>
    ${playerSplits(p, ms, log)}
    <div class="tw" style="margin-top:.8rem"><table><thead><tr><th>Match</th><th>Rating</th><th>Min</th><th>G</th><th>A</th><th>xG</th><th>xA</th><th>Shots</th><th>KP</th><th>Passes</th><th>Tkl</th></tr></thead><tbody>${matchRows}</tbody></table></div></div>`;
}

export function vSeason() {
  const rows = seasonRows(matchList(), roster());
  if (!rows.length) return `<div class="panel empty">Season totals build up as you tag matches and credit players.</div>`;
  const p9 = ui.per90;
  const v = (x, a, dp) => {
    const n = p9 ? (a.mins ? (x / a.mins) * 90 : 0) : x;
    return p9 || dp ? f2(n) : n;
  };
  const table = rows
    .map(
      ({ p, a }) => `<tr><td>${esc(p.name)} <span class="muted small">${esc(p.pos)}</span></td><td>${rateBadge(a.rating)}</td><td>${a.apps}</td><td>${a.mins}</td>
    <td>${v(a.goals, a)}</td><td>${v(a.assists, a)}</td><td>${v(a.xg, a, 1)}</td><td>${v(a.xa, a, 1)}</td><td>${f2(a.goals - a.xg)}</td><td>${v(a.shots, a)}</td><td>${v(a.sot, a)}</td><td>${v(a.kp, a)}</td>
    <td>${a.passA ? Math.round((a.passC / a.passA) * 100) + '%' : '–'}</td><td>${v(a.drbW, a)}</td><td>${v(a.tklW, a)}</td><td>${v(a.int, a)}</td><td>${v(a.rec, a)}</td></tr>`,
    )
    .join('');
  const ms = chronMatches(matchList());
  return `<div class="panel"><div class="row" style="justify-content:space-between;margin-bottom:.6rem"><h2 style="margin:0">Season</h2>
    <div class="row"><div class="seg"><button class="plain" data-a="p90" data-v="0" aria-pressed="${!p9}">Totals</button><button class="plain" data-a="p90" data-v="1" aria-pressed="${p9}">Per 90</button></div>
    <button class="btn" data-a="csv">Export CSV</button></div></div>
  <div class="tw"><table><thead><tr><th>Player</th><th>Avg rating</th><th>Apps</th><th>Min</th><th>G</th><th>A</th><th>xG</th><th>xA</th><th>G−xG</th><th>Shots</th><th>SoT</th><th>KP</th><th>Pass %</th><th>Drb</th><th>Tkl</th><th>Int</th><th>Rec</th></tr></thead><tbody>${table}</tbody></table></div>
  <p class="hint">G−xG above zero means finishing better than the chances suggest.</p></div>
  ${teamPanel(ms)}${zonesPanel(ms, 'season')}${playerPanel(rows, ms)}
  ${glossaryPanel(['rating', 'p90', 'xg', 'xa', 'gxg', 'zones', 'form', 'onoff', 'formation'])}`;
}
