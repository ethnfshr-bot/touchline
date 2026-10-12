import { describe, expect, it } from 'vitest';
import { matchToVideo, retimeEvents, videoToMatch } from '../src/engine/videotime.js';

// Recording starts 3:00 before kick-off; second half kicks off 52:00 into the video.
const sync = { k1: 180, k2: 52 * 60 };

describe('videoToMatch', () => {
  it('treats the video start as kick-off when nothing is marked', () => {
    expect(videoToMatch(125, undefined, 45)).toBe(125);
    expect(videoToMatch(125, {}, 45)).toBe(125);
  });

  it('subtracts the first-half kick-off', () => {
    expect(videoToMatch(180, sync, 45)).toBe(0);
    expect(videoToMatch(180 + 600, sync, 45)).toBe(600);
  });

  it('clamps pre-match footage to 0', () => {
    expect(videoToMatch(60, sync, 45)).toBe(0);
  });

  it('keeps counting through first-half stoppage time', () => {
    expect(videoToMatch(180 + 47 * 60, sync, 45)).toBe(47 * 60);
  });

  it('restarts from the half length at the second-half kick-off', () => {
    expect(videoToMatch(52 * 60, sync, 45)).toBe(45 * 60);
    expect(videoToMatch(52 * 60 + 90, sync, 45)).toBe(45 * 60 + 90);
    expect(videoToMatch(52 * 60 + 90, sync, 30)).toBe(30 * 60 + 90);
  });
});

describe('matchToVideo', () => {
  it('inverts videoToMatch in both halves', () => {
    for (const t of [0, 600, 44 * 60, 45 * 60, 60 * 60, 93 * 60]) {
      expect(videoToMatch(matchToVideo(t, sync, 45), sync, 45)).toBe(t);
    }
  });

  it('works with only the first kick-off marked', () => {
    expect(matchToVideo(60 * 60, { k1: 30 }, 45)).toBe(30 + 3600);
  });
});

describe('retimeEvents', () => {
  it('recomputes times from video positions and re-sorts', () => {
    const events = [
      { id: 'a', t: 999, vt: 52 * 60 + 30 }, // 2nd half, 45:30
      { id: 'b', t: 5, vt: 180 + 75.9 }, // 1st half, 1:15
      { id: 'c', t: 400 }, // tagged without video: left alone
    ];
    retimeEvents(events, sync, 45);
    expect(events.map((e) => [e.id, e.t])).toEqual([['b', 75], ['c', 400], ['a', 45 * 60 + 30]]);
  });
});
