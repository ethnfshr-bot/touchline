import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Relative asset paths so the build works under a GitHub Pages sub-path.
  base: './',
  test: {
    environment: 'node',
  },
});
