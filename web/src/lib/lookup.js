// The lookup island's payload: only the records it can actually answer for.
//
// A scored course is answerable. So is a course Coursera explicitly marks as
// having no written reviews — that is a real answer ("nothing to weigh yet").
// A failed scrape is neither: it has no score and no course state a visitor can
// act on, and passing it through made `starisk.toFixed` throw at runtime.

/**
 * The course key for a pasted URL, path, or bare slug.
 *
 * A bare slug is a course, matching `starisk.add`'s v1 rule: `x`, `/learn/x`,
 * `learn/x`, and a full Coursera URL all normalise to `learn/x`.
 *
 * @param {string} input
 * @returns {string}
 */
export function normalizeCourseKey(input) {
  const match = input.trim().match(/coursera\.org\/([^/?#]+)\/([^/?#]+)/);
  if (match) return `${match[1]}/${match[2]}`;

  const cleaned = input.trim().replace(/^\/+|\/+$/g, '');
  if (!cleaned) return cleaned;
  return cleaned.includes('/') ? cleaned : `learn/${cleaned}`;
}

/**
 * @param {Record<string, any>} scores
 * @returns {Record<string, any>}
 */
export function buildLookup(scores) {
  return Object.fromEntries(
    Object.entries(scores)
      .filter(([, record]) => typeof record.starisk === 'number' || record.no_reviews === true)
      .map(([key, record]) => [
        key,
        {
          title: record.title,
          slug: record.slug ?? key,
          coursera: record.coursera ?? null,
          starisk: record.starisk,
          reviews: record.reviews,
          reviews_total: record.reviews_total,
          ratings_total: record.ratings_total,
          no_reviews: record.no_reviews === true,
        },
      ]),
  );
}
