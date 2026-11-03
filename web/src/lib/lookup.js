// The lookup island's payload: only the records it can actually answer for.
//
// A scored course is answerable. So is a course Coursera explicitly marks as
// having no written reviews — that is a real answer ("nothing to weigh yet").
// A failed scrape is neither: it has no score and no course state a visitor can
// act on, and passing it through made `starisk.toFixed` throw at runtime.

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
