export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const sum = (arr, f) => arr.reduce((acc, e) => acc + f(e), 0);
export const avgOf = (arr) => (arr.length ? arr.reduce((x, y) => x + y, 0) / arr.length : null);
export const f1 = (v) => (Math.round(v * 10) / 10).toFixed(1);
export const f2 = (v) => (Math.round(v * 100) / 100).toFixed(2);
