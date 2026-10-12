import { clamp } from './util.js';

export const PITCH_LENGTH = 105;
export const PITCH_WIDTH = 68;
export const GOAL_WIDTH = 7.32;
export const PENALTY_XG = 0.76;

/**
 * Hand-tuned logistic model: logit = intercept + distance*d + angle*a.
 * These coefficients were chosen by eye, not fitted. Phase 2 replaces them
 * with a model trained on StatsBomb open data.
 */
export const COEF = { intercept: -0.5, distance: -0.13, angle: 1.5 };
export const HEADER_FACTOR = 0.55;
export const BIG_CHANCE_FACTOR = 1.6;
export const BIG_CHANCE_FLOOR = 0.3;
export const XG_MIN = 0.01;
export const XG_MAX = 0.95;

/**
 * Distance (metres) and open goal-mouth angle (radians) for a shot.
 * Event coordinates are 0–100 in the shooting team's frame (attacking towards x = 100).
 */
export function shotGeometry(e) {
  const X = ((100 - e.x) / 100) * PITCH_LENGTH;
  const Y = ((e.y - 50) / 100) * PITCH_WIDTH;
  const half = GOAL_WIDTH / 2;
  let angle = Math.atan2(GOAL_WIDTH * X, X * X + Y * Y - half * half);
  if (angle < 0) angle += Math.PI;
  return { distance: Math.hypot(X, Y), angle };
}

/**
 * Expected goals for one shot event. Shots without a known location (`noloc`,
 * e.g. goals detected automatically from the restart) count as 0: better an
 * honest gap than an invented position.
 */
export function xgOf(e) {
  if (e.noloc) return 0;
  if (e.pen) return PENALTY_XG;
  const { distance, angle } = shotGeometry(e);
  let g = 1 / (1 + Math.exp(-(COEF.intercept + COEF.distance * distance + COEF.angle * angle)));
  if (e.header) g *= HEADER_FACTOR;
  if (e.big) g = Math.max(g * BIG_CHANCE_FACTOR, BIG_CHANCE_FLOOR);
  return clamp(g, XG_MIN, XG_MAX);
}
