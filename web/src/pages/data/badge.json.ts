import type { APIRoute } from 'astro';
import scores from '../../data/scores.json';
import groupings from '../../data/groupings.json';
import requests from '../../data/requests.json';
import { buildBadge } from '../../lib/badge.js';

// The bookmarklet's copy of the data: five fields per course instead of the whole
// record, and only the records a badge can render. Built from the same imports as
// `/data/scores.json`, which stays the dataset download (IDEAS.md I6).
export const GET: APIRoute = () =>
  new Response(JSON.stringify(buildBadge(scores, groupings, requests)), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
