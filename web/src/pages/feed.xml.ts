import type { APIRoute } from 'astro';

import requests from '../data/requests.json';
import scores from '../data/scores.json';
import groupings from '../data/groupings.json';
import { buildWanted } from '../lib/wanted.js';
import { buildFeed } from '../lib/feed.js';

export const GET: APIRoute = ({ site }) => {
  const { fulfilled } = buildWanted(requests, scores, groupings);
  const xml = buildFeed(
    fulfilled,
    site?.href ?? 'https://starisk.pages.dev',
    requests.generatedAt,
  );

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/atom+xml; charset=utf-8',
      'Cache-Control': 'public, max-age=300',
    },
  });
};
