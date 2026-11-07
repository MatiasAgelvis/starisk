// POST /api/course-request — the Vercel entry point.
//
// The logic lives in `src/lib/course-requests.js` so the host stays swappable;
// this file only supplies the environment and picks a runtime. Edge keeps the
// function on the same Web APIs the logic already uses (Request, Response,
// crypto.subtle) with no Node compatibility layer.

import { handleCourseRequest } from '../src/lib/course-requests.js';

export const config = { runtime: 'edge' };

export default function handler(request) {
  return handleCourseRequest({ request, env: process.env });
}
