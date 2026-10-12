import { halfLen } from '../engine/stats.js';
import { matchToVideo, videoToMatch } from '../engine/videotime.js';
import { setClockSource } from './clock.js';
import { $ } from './dom.js';
import { ui } from './state.js';

/*
 * One video player at a time, shown in #player (inside the sticky header, outside
 * the re-rendered #app so playback survives render()). Two backends share one shape:
 *   { kind, matchId, currentTime(), seek(s), play(), pause(), paused(), destroy() }
 * Local files play from an object URL and are never uploaded or stored.
 * YouTube uses the official IFrame Player API in privacy-enhanced mode.
 */

let player = null;
let hooks = { state: () => {}, error: () => {} };

/** state(): playback started/paused. error(message): the video can't be played. */
export function setPlayerHooks(h) {
  hooks = { ...hooks, ...h };
}

export const videoActive = () => !!player && player.matchId === ui.active;
export const videoTime = () => (player ? player.currentTime() : 0);
export const isPaused = () => !player || player.paused();

export function seekVideo(sec) {
  if (player) player.seek(Math.max(0, sec));
}

export function seekMatch(t, m) {
  seekVideo(matchToVideo(t, m.video, halfLen(m)));
}

export function togglePlay() {
  if (!player) return;
  if (player.paused()) player.play();
  else player.pause();
}

export function unloadVideo() {
  if (player) player.destroy();
  player = null;
  setClockSource(null);
  const host = $('#player-host');
  if (host) host.innerHTML = '';
}

function attach(p, m) {
  player = p;
  setClockSource(() => videoToMatch(p.currentTime(), m.video, halfLen(m)));
  hooks.state();
}

/** Keep the kick-off marks only if it's the same video as last time. */
function setSource(m, source, ident) {
  const prev = m.video || {};
  const same = prev.source === source && (source === 'file' ? prev.name === ident.name : prev.youtubeId === ident.youtubeId);
  m.video = same ? { ...prev, ...ident, source } : { source, ...ident };
}

export function loadFile(file, m) {
  unloadVideo();
  setSource(m, 'file', { name: file.name });
  const url = URL.createObjectURL(file);
  const v = document.createElement('video');
  v.controls = true;
  v.playsInline = true;
  v.preload = 'auto';
  v.src = url;
  v.addEventListener('play', () => hooks.state());
  v.addEventListener('pause', () => hooks.state());
  v.addEventListener('error', () =>
    hooks.error("This browser can't play that file. MP4 (H.264) works everywhere; try converting it with HandBrake or VLC."),
  );
  $('#player-host').appendChild(v);
  attach(
    {
      kind: 'file',
      matchId: m.id,
      currentTime: () => v.currentTime,
      seek: (s) => (v.currentTime = s),
      play: () => v.play().catch(() => {}),
      pause: () => v.pause(),
      paused: () => v.paused,
      destroy: () => {
        v.removeAttribute('src');
        v.load();
        URL.revokeObjectURL(url);
      },
    },
    m,
  );
}

let ytApi = null;
function loadYouTubeApi() {
  if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
  if (!ytApi) {
    ytApi = new Promise((resolve, reject) => {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        if (prev) prev();
        resolve(window.YT);
      };
      const s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.onerror = () => {
        ytApi = null;
        reject(new Error('blocked'));
      };
      document.head.appendChild(s);
    });
  }
  return ytApi;
}

const YT_ERRORS = {
  2: "That doesn't look like a valid YouTube video.",
  5: "YouTube couldn't play this video in the browser.",
  100: 'That YouTube video is private or has been removed. Use Public or Unlisted.',
  101: "The video's owner doesn't allow it to be embedded. Turn on \"Allow embedding\" in YouTube Studio.",
  150: "The video's owner doesn't allow it to be embedded. Turn on \"Allow embedding\" in YouTube Studio.",
};

export async function loadYouTube(id, m) {
  unloadVideo();
  setSource(m, 'youtube', { youtubeId: id });
  let YT;
  try {
    YT = await loadYouTubeApi();
  } catch {
    hooks.error("Couldn't reach YouTube. Check your connection or any content blocker.");
    return;
  }
  if (ui.active !== m.id) return; // switched match while loading
  const host = $('#player-host');
  host.innerHTML = '<div id="yt-player"></div>';
  const yp = new YT.Player('yt-player', {
    host: 'https://www.youtube-nocookie.com',
    videoId: id,
    playerVars: { playsinline: 1, rel: 0 },
    events: {
      onStateChange: () => hooks.state(),
      onError: (e) => hooks.error(YT_ERRORS[e.data] || "YouTube couldn't play this video."),
    },
  });
  attach(
    {
      kind: 'youtube',
      matchId: m.id,
      currentTime: () => (yp.getCurrentTime ? yp.getCurrentTime() || 0 : 0),
      seek: (s) => yp.seekTo && yp.seekTo(s, true),
      play: () => yp.playVideo && yp.playVideo(),
      pause: () => yp.pauseVideo && yp.pauseVideo(),
      paused: () => !yp.getPlayerState || yp.getPlayerState() !== YT.PlayerState.PLAYING,
      destroy: () => yp.destroy && yp.destroy(),
    },
    m,
  );
}
