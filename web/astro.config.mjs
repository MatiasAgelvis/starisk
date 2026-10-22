import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // Canonical + Open Graph URLs need an absolute origin. Override with
  // SITE_URL=https://your.domain when the domain changes.
  site: process.env.SITE_URL ?? 'https://starisk.pages.dev',
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
  },
});
