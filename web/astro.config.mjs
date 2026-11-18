import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import tailwindcss from '@tailwindcss/vite';

import { DEFAULT_SITE } from './src/lib/site.js';

export default defineConfig({
  // Canonical + Open Graph URLs need an absolute origin. The default is
  // production; SITE_URL overrides it, which is what a preview deploy wants.
  site: process.env.SITE_URL ?? DEFAULT_SITE,
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
  },
});
