/**
 * Match clock, in seconds of match time. Either a manual stopwatch run alongside
 * the video, or driven by the loaded video player (see video.js).
 */
export const clock = { running: false, base: 0, at: 0 };

let source = null;
/** Let a video player drive the clock. Pass null to go back to the manual clock. */
export function setClockSource(fn) {
  source = fn;
}

export const nowSec = () => (source ? source() : clock.base + (clock.running ? (Date.now() - clock.at) / 1000 : 0));

export function setClock(sec) {
  clock.base = Math.max(0, sec);
  clock.at = Date.now();
}

export const fmt = (s) => {
  s = Math.max(0, Math.floor(s));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};

/** "23:40" or "23" -> seconds, or null if unparseable. */
export function parseClock(v) {
  const m = String(v).trim().match(/^(\d{1,3})(?::(\d{1,2}))?$/);
  return m ? Number(m[1]) * 60 + Number(m[2] || 0) : null;
}
