import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

import { DEFAULT_SITE } from './src/lib/site.js';

export default defineConfig({
  // Canonical + Open Graph URLs need an absolute origin. The default is
  // production; SITE_URL overrides it, which is what a preview deploy wants.
  site: process.env.SITE_URL ?? DEFAULT_SITE,
  integrations: [
    svelte(),
    // ~1,700 pages and, until now, nothing pointing a crawler at them. /request
    // is noindex, so it stays out of the map.
    sitemap({ filter: (page) => !new URL(page).pathname.startsWith('/request') }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
