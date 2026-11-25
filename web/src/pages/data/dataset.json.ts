import type { APIRoute } from 'astro';
import scores from '../../data/scores.json';
import groupings from '../../data/groupings.json';
import { buildDataset } from '../../lib/dataset.js';

// The citable dataset (IDEAS.md I6): measurements and identifiers only. Served at
// /data/dataset.json so the CDN headers for /data/* apply — CORS open, five-minute
// cache. `/data/scores.json` stays the raw build input, which quotes reviews.
export const GET: APIRoute = () =>
  new Response(JSON.stringify(buildDataset(scores, groupings, new Date().toISOString())), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
