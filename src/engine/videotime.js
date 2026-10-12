/*
 * Mapping between video time and match time.
 *
 * A match's `video` sync record is { name, k1, k2 }:
 *   k1  seconds into the video at first-half kick-off (default 0)
 *   k2  seconds into the video at second-half kick-off (optional)
 * Match time `t` is seconds since kick-off, with the second half starting at
 * halfMinutes * 60, the same convention as the manual clock.
 */

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** Video seconds -> match seconds. Footage before kick-off clamps to 0. */
export function videoToMatch(vt, sync, halfMinutes) {
  const s = sync || {};
  if (isNum(s.k2) && vt >= s.k2) return halfMinutes * 60 + (vt - s.k2);
  return Math.max(0, vt - (isNum(s.k1) ? s.k1 : 0));
}

/**
 * Match seconds -> video seconds. Times at or after the half length map into the
 * second half when k2 is set, so first-half stoppage time can't be addressed this way.
 */
export function matchToVideo(t, sync, halfMinutes) {
  const s = sync || {};
  const halfSec = halfMinutes * 60;
  if (isNum(s.k2) && t >= halfSec) return s.k2 + (t - halfSec);
  return (isNum(s.k1) ? s.k1 : 0) + t;
}

/** Recompute match times for events that carry a video time `vt`, after the sync changes. */
export function retimeEvents(events, sync, halfMinutes) {
  events.forEach((e) => {
    if (isNum(e.vt)) e.t = Math.floor(videoToMatch(e.vt, sync, halfMinutes));
  });
  events.sort((a, b) => a.t - b.t);
  return events;
}
