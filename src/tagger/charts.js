import { ACT, isShot } from '../engine/actions.js';
import { ratingBand } from '../engine/rating.js';
import { halfLen, thirds } from '../engine/stats.js';
import { clamp, f1, f2 } from '../engine/util.js';
import { xgOf } from '../engine/xg.js';
import { esc } from './dom.js';
import { pitchSVG, toScreen } from './pitch.js';
import { pName } from './state.js';

const minuteOf = (e) => Math.floor(e.t / 60) + 1;

export const rateBadge = (r) =>
  r == null ? '<span class="muted">–</span>' : `<span class="rate" style="background:var(--${ratingBand(r)})">${f1(r)}</span>`;

/** Two-sided comparison bar: us on the left, them on the right. */
export function cmpRow(label, a, b, fa, fb) {
  const tot = a + b;
  const pa = tot ? (a / tot) * 100 : 50;
  return `<div class="cmp"><div class="v">${fa != null ? fa : a}</div><div class="lab">${label}</div><div class="v r">${fb != null ? fb : b}</div>
  <div class="bars"><i style="width:${pa}%;background:var(--us)"></i><i style="width:${100 - pa}%;background:var(--them)"></i></div></div>`;
}

export function xgRace(m) {
  const W = 320, H = 150, pl = 26, pb = 20, pt = 10, pr = 8;
  const shots = m.events.filter(isShot).sort((a, b) => a.t - b.t);
  const maxMin = Math.max(halfLen(m) * 2, ...shots.map(minuteOf));
  let cu = 0, ct = 0;
  const pu = [[0, 0]], pth = [[0, 0]], goals = [];
  shots.forEach((e) => {
    const mn = minuteOf(e);
    const g = xgOf(e);
    if (e.team === 'us') {
      pu.push([mn, cu]);
      cu += g;
      pu.push([mn, cu]);
      if (e.type === 'goal') goals.push(['us', mn, cu]);
    } else {
      pth.push([mn, ct]);
      ct += g;
      pth.push([mn, ct]);
      if (e.type === 'goal') goals.push(['them', mn, ct]);
    }
  });
  pu.push([maxMin, cu]);
  pth.push([maxMin, ct]);
  const maxY = Math.max(1, Math.ceil(Math.max(cu, ct) * 2) / 2);
  const X = (v) => pl + (v / maxMin) * (W - pl - pr);
  const Y = (v) => H - pb - (v / maxY) * (H - pb - pt);
  const path = (p) => 'M' + p.map((q) => X(q[0]).toFixed(1) + ' ' + Y(q[1]).toFixed(1)).join(' L');
  let grid = '';
  for (let v = 0; v <= maxY + 1e-9; v += maxY > 2 ? 1 : 0.5) {
    grid += `<line x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" stroke-width=".6"/><text x="${pl - 4}" y="${Y(v) + 3}" font-size="8" text-anchor="end" fill="var(--muted)">${v}</text>`;
  }
  const ht = X(halfLen(m));
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" role="img" aria-label="Cumulative xG over the match">${grid}
  <line x1="${ht}" x2="${ht}" y1="${pt}" y2="${H - pb}" stroke="var(--muted)" stroke-dasharray="2 2" stroke-width=".6"/><text x="${ht}" y="${H - 6}" font-size="8" text-anchor="middle" fill="var(--muted)">HT</text>
  <text x="${pl}" y="${H - 6}" font-size="8" fill="var(--muted)">0'</text><text x="${W - pr}" y="${H - 6}" font-size="8" text-anchor="end" fill="var(--muted)">${maxMin}'</text>
  <path d="${path(pth)}" fill="none" stroke="var(--them)" stroke-width="2"/><path d="${path(pu)}" fill="none" stroke="var(--us)" stroke-width="2"/>
  ${goals.map((g) => `<circle cx="${X(g[1])}" cy="${Y(g[2])}" r="3.5" fill="${g[0] === 'us' ? 'var(--us)' : 'var(--them)'}" stroke="var(--panel)" stroke-width="1.2"/>`).join('')}</svg>`;
}

export function shotMap(m, onlyPid) {
  const shots = m.events.filter((e) => isShot(e) && !e.noloc && (!onlyPid || (e.team === 'us' && e.pid === onlyPid)));
  const inner = shots
    .map((e) => {
      const p = toScreen(e.team, e.x, e.y);
      const g = xgOf(e);
      const r = 0.9 + Math.sqrt(g) * 3.4;
      const col = e.team === 'us' ? 'var(--us)' : 'var(--them)';
      const fill = e.type === 'goal' ? col : e.type === 'saved' ? 'rgba(255,255,255,.55)' : 'none';
      return `<circle cx="${p.sx.toFixed(2)}" cy="${p.sy.toFixed(2)}" r="${r.toFixed(2)}" fill="${fill}" stroke="${e.type === 'goal' ? '#fff' : col}" stroke-width="${e.type === 'goal' ? 0.5 : 0.7}"><title>${minuteOf(e)}' ${esc(e.team === 'us' ? pName(e.pid) : 'Opposition')} ${ACT[e.type].l}, ${f2(g)} xG</title></circle>`;
    })
    .join('');
  return pitchSVG(inner);
}

export function thirdsSVG(m) {
  const z = thirds(m);
  const inner =
    z
      .map((c, i) => {
        const tot = c[0] + c[1];
        const pu = tot ? Math.round((c[0] / tot) * 100) : null;
        const x = i * 35;
        return `<rect x="${x}" y="0" width="35" height="68" fill="var(--us)" opacity="${pu == null ? 0 : ((pu / 100) * 0.55).toFixed(2)}"/>
    <text x="${x + 17.5}" y="31" font-size="7" font-weight="700" text-anchor="middle" fill="#fff" font-family="Barlow Condensed">${pu == null ? '–' : pu + '%'}</text>
    <text x="${x + 17.5}" y="40" font-size="3.4" text-anchor="middle" fill="var(--chalk)" font-family="Barlow">${pu == null ? 'no data' : 'them ' + (100 - pu) + '%'}</text>`;
      })
      .join('') +
    `<line x1="35" y1="0" x2="35" y2="68" stroke="#fff" stroke-dasharray="1.2 1.2" stroke-width=".35"/><line x1="70" y1="0" x2="70" y2="68" stroke="#fff" stroke-dasharray="1.2 1.2" stroke-width=".35"/>
    <text x="94" y="66" font-size="2.6" fill="var(--chalk)" text-anchor="middle" font-family="Barlow Condensed">You attack →</text>`;
  return pitchSVG(inner);
}

export function heatmap(m, pid) {
  const ev = m.events.filter((e) => e.team === 'us' && e.pid === pid && !e.noloc);
  const C = 12, R = 8;
  const g = Array.from({ length: R }, () => Array(C).fill(0));
  let mx = 0;
  ev.forEach((e) => {
    const cx = clamp(Math.floor((e.x / 100) * C), 0, C - 1);
    const cy = clamp(Math.floor((e.y / 100) * R), 0, R - 1);
    g[cy][cx]++;
    mx = Math.max(mx, g[cy][cx]);
  });
  let inner = '';
  if (mx) {
    for (let y = 0; y < R; y++) {
      for (let x = 0; x < C; x++) {
        if (g[y][x]) inner += `<rect x="${(x * 105) / C}" y="${(y * 68) / R}" width="${105 / C}" height="${68 / R}" fill="var(--gold)" opacity="${(0.15 + (0.7 * g[y][x]) / mx).toFixed(2)}"/>`;
      }
    }
  }
  return pitchSVG(inner + `<text x="94" y="66" font-size="2.6" fill="var(--chalk)" text-anchor="middle" font-family="Barlow Condensed">Attacking →</text>`);
}

/** Pitch split into 3x3 zones shaded by count; grid from engine/zones.js. */
export function zoneMap(grid, colour, label) {
  const max = Math.max(1, ...grid.flat());
  let inner = '';
  for (let t = 0; t < 3; t++) {
    for (let c = 0; c < 3; c++) {
      const n = grid[t][c];
      const x = t * 35, y = c * (68 / 3);
      inner += `<rect x="${x}" y="${y.toFixed(2)}" width="35" height="${(68 / 3).toFixed(2)}" fill="${colour}" opacity="${n ? (0.15 + (0.65 * n) / max).toFixed(2) : 0}"/>`;
      if (n) inner += `<text x="${x + 17.5}" y="${(y + 68 / 6 + 2.5).toFixed(2)}" font-size="7" font-weight="700" text-anchor="middle" fill="#fff" font-family="Barlow Condensed">${n}</text>`;
    }
  }
  inner += `<text x="94" y="66" font-size="2.6" fill="var(--chalk)" text-anchor="middle" font-family="Barlow Condensed">You attack →</text>`;
  return pitchSVG(inner, null, '').replace('aria-label="Pitch"', `aria-label="${esc(label)}"`);
}

const niceStep = (r) => (r <= 2 ? 0.5 : r <= 5 ? 1 : r <= 12 ? 2 : 5);

function gridY(lo, hi, st, Y, pl, W, pr) {
  let g = '';
  for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) {
    g += `<line x1="${pl}" x2="${W - pr}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line)" stroke-width=".6"/><text x="${pl - 4}" y="${(Y(v) + 3).toFixed(1)}" font-size="8" text-anchor="end" fill="var(--muted)">${+v.toFixed(1)}</text>`;
  }
  return g;
}

/** series: [{vals: (number|null)[], color, dash?, dots?}] */
export function lineChart(series, labels, opt = {}) {
  const W = 320, H = 160, pl = 28, pr = 10, pt = 10, pb = 24, n = labels.length;
  const all = [].concat(...series.map((s) => s.vals.filter((v) => v != null)));
  const lo = opt.min != null ? opt.min : Math.min(0, ...all);
  let hi = opt.max != null ? opt.max : Math.max(1, ...all);
  if (hi <= lo) hi = lo + 1;
  const X = (i) => (n < 2 ? (W + pl - pr) / 2 : pl + (i / (n - 1)) * (W - pl - pr));
  const Y = (v) => H - pb - ((v - lo) / (hi - lo)) * (H - pb - pt);
  let g = gridY(lo, hi, opt.step || niceStep(hi - lo), Y, pl, W, pr);
  const every = Math.max(1, Math.ceil(n / 6));
  labels.forEach((l, i) => {
    if (i % every === 0 || i === n - 1) g += `<text x="${X(i).toFixed(1)}" y="${H - 8}" font-size="7.5" text-anchor="middle" fill="var(--muted)">${esc(l)}</text>`;
  });
  const lines = series
    .map((s) => {
      let d = '';
      let pen = false;
      s.vals.forEach((v, i) => {
        if (v == null) {
          pen = false;
          return;
        }
        d += (pen ? ' L' : ' M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1);
        pen = true;
      });
      const dots =
        s.dots === false
          ? ''
          : s.vals.map((v, i) => (v == null ? '' : `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="2.6" fill="${s.color}"><title>${esc(labels[i])}: ${f2(v)}</title></circle>`)).join('');
      return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.dash ? 1.3 : 2}" ${s.dash ? 'stroke-dasharray="4 3"' : ''}/>${dots}`;
    })
    .join('');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" role="img" aria-label="${esc(opt.label || 'Chart')}">${g}${lines}</svg>`;
}

/** pairs: [[xG for, xG against], ...] */
export function barChart(pairs, labels, label) {
  const W = 320, H = 160, pl = 28, pr = 10, pt = 10, pb = 24, n = labels.length;
  const hi = Math.max(1, ...[].concat(...pairs));
  const st = niceStep(hi);
  const top = Math.ceil(hi / st) * st;
  const Y = (v) => H - pb - (v / top) * (H - pb - pt);
  const bw = (W - pl - pr) / n;
  const every = Math.max(1, Math.ceil(n / 6));
  let g = gridY(0, top, st, Y, pl, W, pr);
  pairs.forEach((p, i) => {
    const cx = pl + i * bw + bw / 2;
    const w = Math.min(10, bw * 0.38);
    g += `<rect x="${(cx - w).toFixed(1)}" y="${Y(p[0]).toFixed(1)}" width="${w.toFixed(1)}" height="${(H - pb - Y(p[0])).toFixed(1)}" fill="var(--us)"><title>${esc(labels[i])}: ${f2(p[0])} xG for</title></rect><rect x="${cx.toFixed(1)}" y="${Y(p[1]).toFixed(1)}" width="${w.toFixed(1)}" height="${(H - pb - Y(p[1])).toFixed(1)}" fill="var(--them)"><title>${esc(labels[i])}: ${f2(p[1])} xG against</title></rect>`;
    if (i % every === 0 || i === n - 1) g += `<text x="${cx.toFixed(1)}" y="${H - 8}" font-size="7.5" text-anchor="middle" fill="var(--muted)">${esc(labels[i])}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" role="img" aria-label="${esc(label)}">${g}</svg>`;
}
