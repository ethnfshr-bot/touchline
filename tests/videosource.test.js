import { describe, expect, it } from 'vitest';
import { parseYouTubeId } from '../src/engine/videosource.js';

const ID = 'dQw4w9WgXcQ';

describe('parseYouTubeId', () => {
  it.each([
    `https://www.youtube.com/watch?v=${ID}`,
    `https://youtube.com/watch?v=${ID}&t=120s`,
    `https://m.youtube.com/watch?feature=share&v=${ID}`,
    `https://youtu.be/${ID}`,
    `https://youtu.be/${ID}?si=abc&t=30`,
    `https://www.youtube.com/embed/${ID}`,
    `https://www.youtube-nocookie.com/embed/${ID}`,
    `https://www.youtube.com/shorts/${ID}`,
    `https://www.youtube.com/live/${ID}?feature=share`,
    `  https://youtu.be/${ID}  `,
  ])('reads %s', (url) => {
    expect(parseYouTubeId(url)).toBe(ID);
  });

  it.each([
    '',
    'not a url',
    `https://app.veo.co/matches/${ID}/`,
    'https://www.youtube.com/watch?v=short',
    'https://www.youtube.com/channel/UCabcdefghijk',
    `https://evil.example/watch?v=${ID}`,
    `https://youtube.com.evil.example/watch?v=${ID}`,
    `javascript:alert(1)//youtu.be/${ID}`,
  ])('rejects %s', (url) => {
    expect(parseYouTubeId(url)).toBeNull();
  });
});
