/*
 * Recognising video links. Pure functions, no DOM.
 */

const YT_ID = /^[A-Za-z0-9_-]{11}$/;

/**
 * Extract a YouTube video id from a link, or return null.
 * Accepts watch, youtu.be, embed, shorts and live links, with or without extra parameters.
 */
export function parseYouTubeId(input) {
  let url;
  try {
    url = new URL(String(input).trim());
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  const host = url.hostname.replace(/^(www\.|m\.|music\.)/, '');
  let id = null;
  if (host === 'youtu.be') {
    id = url.pathname.split('/')[1];
  } else if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
    if (url.pathname === '/watch') id = url.searchParams.get('v');
    else {
      const m = url.pathname.match(/^\/(embed|shorts|live|v)\/([^/]+)/);
      if (m) id = m[2];
    }
  }
  return id && YT_ID.test(id) ? id : null;
}

export const isYouTubeId = (id) => typeof id === 'string' && YT_ID.test(id);
