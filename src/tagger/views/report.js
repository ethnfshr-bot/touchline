import { matchRatings } from '../../engine/rating.js';
import { posPlayed, score, sortedMatches, teamStats } from '../../engine/stats.js';
import { f2 } from '../../engine/util.js';
import { cmpRow, heatmap, rateBadge, shotMap, thirdsSVG, xgRace } from '../charts.js';
import { esc } from '../dom.js';
import { matchList, roster, store, ui } from '../state.js';

const pct = (a, b) => (b ? Math.round((a / b) * 100) + '%' : '–');

function ratingsTable(m, ps, best) {
  const rows = ps
    .map(
      (x) => `<tr><td><button class="btn" style="padding:.15rem .5rem" data-a="focus" data-id="${esc(x.p.id)}">${best && best.p.id === x.p.id && x.r != null ? '<span class="potm" aria-label="Player of the match">★</span> ' : ''}${esc(x.p.name)}</button> <span class="muted small">${esc(posPlayed(m, x.p))}</span></td>
    <td>${rateBadge(x.r)}</td><td><input type="number" min="0" max="130" value="${x.mn}" data-mins="${esc(x.p.id)}" aria-label="Minutes for ${esc(x.p.name)}"></td>
    <td>${x.st.goals}</td><td>${x.st.assists}</td><td>${f2(x.st.xg)}</td><td>${f2(x.st.xa)}</td><td>${x.st.shots}</td><td>${x.st.kp}</td>
    <td>${x.st.passC}/${x.st.passC + x.st.passL}</td><td>${x.st.drbW}/${x.st.drbW + x.st.drbL}</td><td>${x.st.tklW}</td><td>${x.st.int}</td><td>${x.st.rec}</td><td>${x.st.touches}</td></tr>`,
    )
    .join('');
  return `<div class="tw"><table><thead><tr><th>Player</th><th>Rating</th><th>Min</th><th>G</th><th>A</th><th>xG</th><th>xA</th><th>Shots</th><th>KP</th><th>Passes</th><th>Drb</th><th>Tkl</th><th>Int</th><th>Rec</th><th>Touches</th></tr></thead><tbody>${rows}</tbody></table></div>
  <p class="hint">Ratings use Touchline's own FotMob-style formula from the events you tag (FotMob's real model is private). Start at 6.0, tag every action a player makes, and they're comparable match to match. Under 10 minutes, no rating.</p>`;
}

function focusPanel(m, fx) {
  const s = fx.st;
  const stats = [
    ['Goals', s.goals], ['Assists', s.assists], ['xG', f2(s.xg)], ['xA', f2(s.xa)], ['Shots', s.shots], ['On target', s.sot],
    ['Big chances missed', s.bcMiss], ['Key passes', s.kp], ['Pass accuracy', pct(s.passC, s.passC + s.passL)],
    ['Dribbles won', s.drbW + '/' + (s.drbW + s.drbL)], ['Lost ball', s.disp], ['Tackles won', s.tklW + '/' + (s.tklW + s.tklL)], ['Interceptions', s.int],
    ['Recoveries', s.rec], ['Clearances', s.clr], ['Aerials won', s.aerW + '/' + (s.aerW + s.aerL)], ['Fouls', s.fouls], ['Touches', s.touches],
  ];
  return `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(fx.p.name)}</h3>${rateBadge(fx.r)}</div>
    <div class="grid2" style="margin-top:.6rem"><div><div class="muted small" style="margin-bottom:.3rem">Action heatmap</div><div class="pitchwrap">${heatmap(m, fx.p.id)}</div></div>
    <div><div class="muted small" style="margin-bottom:.3rem">Shots</div><div class="pitchwrap">${shotMap(m, fx.p.id)}</div></div></div>
    <div class="statlist">${stats.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('')}</div></div>`;
}

export function vReport() {
  const list = sortedMatches(matchList());
  if (!list.length) return `<div class="panel empty">Tag a match first. Its report appears here.</div>`;
  if (!store.data.matches[ui.reportId]) ui.reportId = store.data.matches[ui.active] ? ui.active : list[0].id;
  const m = store.data.matches[ui.reportId];
  const [u, t] = score(m);
  const A = teamStats(m, 'us');
  const B = teamStats(m, 'them');
  const pos = A.onball + B.onball ? Math.round((A.onball / (A.onball + B.onball)) * 100) : null;
  const tilt = A.ft + B.ft ? Math.round((A.ft / (A.ft + B.ft)) * 100) : null;
  const ps = matchRatings(m, roster());
  const best = ps.reduce((a, b) => (b.r != null && (a == null || b.r > a.r) ? b : a), null);
  ps.sort((a, b) => (b.r == null ? -1 : b.r) - (a.r == null ? -1 : a.r));
  if (!ps.find((x) => x.p.id === ui.focus)) ui.focus = ps[0] ? ps[0].p.id : null;
  const fx = ps.find((x) => x.p.id === ui.focus);
  const opp = esc(m.opp || 'Opponent');
  const sel = `<select id="repsel" aria-label="Match">${list
    .map((x) => {
      const s = score(x);
      return `<option value="${esc(x.id)}" ${x.id === m.id ? 'selected' : ''}>${esc(x.date || '')} vs ${esc(x.opp || 'Opponent')} (${s[0]}–${s[1]})</option>`;
    })
    .join('')}</select>`;
  const passes = (s) => (s.passA ? `${s.passC} (${Math.round((s.passC / s.passA) * 100)}%)` : '0');

  return `<div class="panel">${sel}
    <div class="scoreline" style="margin-top:1rem"><div><div class="t">Us</div><div class="xg">${f2(A.xg)} xG</div></div>
    <div class="s">${u}–${t}</div><div><div class="t">${opp}</div><div class="xg">${f2(B.xg)} xG</div></div></div></div>
  <div class="grid2">
    <div class="panel"><h3>xG race</h3>${xgRace(m)}<div class="legend"><span><i class="dot" style="background:var(--us)"></i>Us</span><span><i class="dot" style="background:var(--them)"></i>${opp}</span><span>Large dots are goals</span></div></div>
    <div class="panel"><h3>Shot map</h3><div class="pitchwrap">${shotMap(m)}</div><div class="legend"><span>Bigger circle, higher xG</span><span>Filled: goal</span><span>Pale: saved</span></div></div>
  </div>
  <div class="grid2">
    <div class="panel"><h3>Possession by thirds</h3><div class="pitchwrap">${thirdsSVG(m)}</div>
      <p class="hint">Share of on-ball actions in each third. Tag opposition actions too, or these read as 100%.</p></div>
    <div class="panel"><h3>Team stats</h3>
      ${pos != null ? cmpRow('Possession', A.onball, B.onball, pos + '%', 100 - pos + '%') : ''}
      ${cmpRow('Expected goals (xG)', A.xg, B.xg, f2(A.xg), f2(B.xg))}
      ${cmpRow('Shots', A.shots, B.shots)}${cmpRow('Shots on target', A.sot, B.sot)}
      ${cmpRow('Big chances', A.big, B.big)}${cmpRow('Big chances missed', A.bigMiss, B.bigMiss)}
      ${cmpRow('Accurate passes', A.passC, B.passC, passes(A), passes(B))}
      ${tilt != null ? cmpRow('Field tilt', A.ft, B.ft, tilt + '%', 100 - tilt + '%') : ''}
      ${cmpRow('Final-third touches', A.ft, B.ft)}${cmpRow('Tackles won', A.tkl, B.tkl)}${cmpRow('Interceptions', A.int, B.int)}
      ${cmpRow('Recoveries', A.rec, B.rec)}${cmpRow('Aerials won', A.aer, B.aer)}${cmpRow('Fouls', A.fouls, B.fouls)}
    </div>
  </div>
  <div class="panel"><h3>Player ratings</h3>${ps.length ? ratingsTable(m, ps, best) : '<p class="muted">Credit tagged actions to squad players to see ratings.</p>'}</div>
  ${fx ? focusPanel(m, fx) : ''}`;
}
