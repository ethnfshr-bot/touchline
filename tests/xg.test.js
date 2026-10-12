import { describe, expect, it } from 'vitest';
import { PENALTY_XG, XG_MAX, XG_MIN, shotGeometry, xgOf } from '../src/engine/xg.js';
import { EDGE_OF_BOX, PEN_SPOT, XG_EDGE_OF_BOX, XG_PEN_SPOT } from './fixtures.js';

describe('shotGeometry', () => {
  it('measures distance in metres from the goal centre', () => {
    expect(shotGeometry(PEN_SPOT).distance).toBeCloseTo(11, 3);
    expect(shotGeometry({ x: 100, y: 0 }).distance).toBeCloseTo(34, 6);
  });

  it('gives the open goal angle', () => {
    // From the penalty spot the goal mouth subtends 2*atan(3.66/11).
    expect(shotGeometry(PEN_SPOT).angle).toBeCloseTo(2 * Math.atan(3.66 / 11), 4);
  });
});

describe('xgOf', () => {
  it('matches reference values from the prototype', () => {
    expect(xgOf(PEN_SPOT)).toBeCloseTo(XG_PEN_SPOT, 10);
    expect(xgOf(EDGE_OF_BOX)).toBeCloseTo(XG_EDGE_OF_BOX, 10);
    expect(xgOf({ x: 90, y: 20 })).toBeCloseTo(0.03698345023478357, 10);
  });

  it('gives penalties a fixed value regardless of position', () => {
    expect(xgOf({ ...PEN_SPOT, pen: 1 })).toBe(PENALTY_XG);
    expect(xgOf({ x: 10, y: 90, pen: 1, header: 1 })).toBe(PENALTY_XG);
  });

  it('gives shots with an unknown position no xG', () => {
    expect(xgOf({ ...PEN_SPOT, noloc: 1 })).toBe(0);
  });

  it('scales headers down', () => {
    expect(xgOf({ ...PEN_SPOT, header: 1 })).toBeCloseTo(XG_PEN_SPOT * 0.55, 10);
  });

  it('boosts big chances with a floor of 0.3', () => {
    expect(xgOf({ ...PEN_SPOT, big: 1 })).toBeCloseTo(XG_PEN_SPOT * 1.6, 10);
    expect(xgOf({ x: 60, y: 50, big: 1 })).toBe(0.3);
  });

  it('clamps to [0.01, 0.95]', () => {
    expect(xgOf({ x: 0, y: 50 })).toBe(XG_MIN);
    expect(xgOf({ x: 50, y: 50 })).toBe(XG_MIN);
    expect(xgOf({ x: 99, y: 50 })).toBe(XG_MAX);
  });

  it('is symmetric about the centre line', () => {
    expect(xgOf({ x: 85, y: 30 })).toBeCloseTo(xgOf({ x: 85, y: 70 }), 12);
  });

  it('falls with distance on a central line', () => {
    const xs = [98, 94, 90, 85, 80, 75];
    const vals = xs.map((x) => xgOf({ x, y: 50 }));
    for (let i = 1; i < vals.length; i++) expect(vals[i]).toBeLessThan(vals[i - 1]);
  });

  it('falls as the angle narrows at the same distance', () => {
    expect(xgOf({ x: 85, y: 35 })).toBeLessThan(xgOf({ x: 85, y: 50 }));
  });
});
