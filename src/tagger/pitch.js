import { clamp } from '../engine/util.js';

/*
 * The pitch SVG is drawn in metres (105 x 68) with our team attacking left to right.
 * Events are stored 0–100 in the acting team's own frame, so opposition events are
 * rotated 180° when drawn. toScreen/toFrame convert between the two.
 */
export function pitchSVG(inner, id, cls) {
  let stripes = '';
  for (let i = 0; i < 6; i++) stripes += `<rect x="${i * 17.5}" y="0" width="17.5" height="68" fill="${i % 2 ? 'var(--grass2)' : 'var(--grass)'}"/>`;
  const L = 'stroke="var(--chalk)" stroke-width=".35" fill="none"';
  return `<svg ${id ? `id="${id}"` : ''} class="pitch ${cls || ''}" viewBox="-2.5 -1.5 110 71" role="img" aria-label="Pitch">
  <rect x="-2.5" y="-1.5" width="110" height="71" fill="var(--grass2)"/>${stripes}
  <rect x="0" y="0" width="105" height="68" ${L}/><line x1="52.5" y1="0" x2="52.5" y2="68" ${L}/>
  <circle cx="52.5" cy="34" r="9.15" ${L}/><circle cx="52.5" cy="34" r=".5" fill="var(--chalk)"/>
  <rect x="0" y="13.84" width="16.5" height="40.32" ${L}/><rect x="88.5" y="13.84" width="16.5" height="40.32" ${L}/>
  <rect x="0" y="24.84" width="5.5" height="18.32" ${L}/><rect x="99.5" y="24.84" width="5.5" height="18.32" ${L}/>
  <circle cx="11" cy="34" r=".45" fill="var(--chalk)"/><circle cx="94" cy="34" r=".45" fill="var(--chalk)"/>
  <path d="M16.5 26.7 A9.15 9.15 0 0 1 16.5 41.3" ${L}/><path d="M88.5 26.7 A9.15 9.15 0 0 0 88.5 41.3" ${L}/>
  <rect x="-1.6" y="30.34" width="1.6" height="7.32" ${L}/><rect x="105" y="30.34" width="1.6" height="7.32" ${L}/>
  ${inner || ''}</svg>`;
}

/** Event frame (0–100, acting team attacks right) -> SVG metres (we attack right). */
export function toScreen(team, x, y) {
  if (team === 'them') {
    x = 100 - x;
    y = 100 - y;
  }
  return { sx: (x / 100) * 105, sy: (y / 100) * 68 };
}

/** SVG metres -> event frame for the given team. */
export function toFrame(team, sx, sy) {
  let x = (sx / 105) * 100;
  let y = (sy / 68) * 100;
  if (team === 'them') {
    x = 100 - x;
    y = 100 - y;
  }
  return { x, y };
}

/** Mouse/touch event -> SVG metres, clamped to the pitch. */
export function svgPoint(svg, evt) {
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return { sx: clamp(p.x, 0, 105), sy: clamp(p.y, 0, 68) };
}
