import { LOSSES, WINS, gridTotal, zoneGrid, zoneInsights } from '../../engine/zones.js';
import { zoneMap } from '../charts.js';
import { esc } from '../dom.js';

/** "Where we win and lose the ball" panel for one or more matches. */
export function zonesPanel(matches, scope) {
  const wins = zoneGrid(matches, WINS);
  const losses = zoneGrid(matches, LOSSES);
  if (gridTotal(wins) + gridTotal(losses) === 0) return '';
  const insights = zoneInsights(wins, losses);
  return `<div class="panel"><h3>Where we win and lose the ball</h3>
    <div class="grid2" style="margin-top:.4rem">
      <div><div class="muted small" style="margin-bottom:.3rem">Ball won (tackles, interceptions, recoveries): ${gridTotal(wins)}</div><div class="pitchwrap">${zoneMap(wins, 'var(--great)', 'Where the ball was won')}</div></div>
      <div><div class="muted small" style="margin-bottom:.3rem">Ball lost (misplaced passes, losing the ball, failed dribbles): ${gridTotal(losses)}</div><div class="pitchwrap">${zoneMap(losses, 'var(--bad)', 'Where the ball was lost')}</div></div>
    </div>
    ${insights.length ? `<div class="story">${insights.map((s) => `<p>${esc(s)}</p>`).join('')}</div>` : `<p class="hint">Tag more ${scope === 'season' ? 'matches' : 'actions'} for observations.</p>`}</div>`;
}
