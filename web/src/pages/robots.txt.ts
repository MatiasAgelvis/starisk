import type { APIRoute } from 'astro';

// Generated rather than static so preview builds point at their own origin.
// /request is the one page with `noindex`, and asking for a course in the
// request form is a write, not something a crawl should explore.
export const GET: APIRoute = ({ site }) => {
  const sitemap = site ? new URL('sitemap-index.xml', site).href : '/sitemap-index.xml';
  const body = ['User-agent: *', 'Allow: /', 'Disallow: /request', '', `Sitemap: ${sitemap}`, ''].join(
    '\n',
  );

  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
