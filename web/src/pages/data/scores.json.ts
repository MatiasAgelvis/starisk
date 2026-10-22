import type { APIRoute } from 'astro';
import scores from '../../data/scores.json';

// The same data the pages are built from, published as a file:
// /data/scores.json. One source, no second copy, and the URL a bookmarklet
// (IDEAS.md I1) or the dataset download (I6) can point at.
export const GET: APIRoute = () =>
  new Response(JSON.stringify(scores, null, 2), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
