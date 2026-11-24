// Programs are the other cut of the course corpus, alongside teachers.
//
// A program is a many-to-many relationship: one program has many courses, and a
// course can belong to several programs. `groupings.json` is the derived
// `programs` table plus its join array; each `courses` entry is a foreign key
// into `scores.json`.

const TYPE_LABELS = {
  specialization: 'Specialization',
  'professional-certificate': 'Professional Certificate',
};

export function typeLabel(type) {
  return TYPE_LABELS[type] ?? 'Program';
}

/**
 * Turn the program index into rows the pages can render.
 *
 * The average weights each course by the reviews we actually read, matching the
 * teacher directory. Courses with no written reviews stay in the list but do not
 * pull on the average.
 *
 * The program's own number is Coursera's pooled rating for the bundle, which the
 * pipeline stores on the grouping entry. It is deliberately not a score: a
 * program page has no written reviews of its own — its review widget belongs to
 * whichever course is selected — so nothing here may come from `scores[key]`.
 */
export function buildGroupings(groupings, scores) {
  const programs = [];

  for (const [key, group] of Object.entries(groupings)) {
    const members = (group.courses ?? []).map((courseKey) => ({
      key: courseKey,
      ...(scores[courseKey] ?? {}),
    }));
    const scored = members.filter((course) => typeof course.starisk === 'number');
    const reviews = scored.reduce((total, course) => total + (course.reviews ?? 0), 0);
    // Why a set is incomplete matters: a course we have never crawled is a crawl
    // away from being measured, while one Coursera shows no written reviews for
    // may never have a score at all.
    const noReviews = members.filter((course) => course.no_reviews === true).length;
    const unread = members.filter(
      (course) => typeof course.starisk !== 'number' && course.no_reviews !== true,
    ).length;

    // The teaching team is inherited, like the average: a program has no roster of
    // its own, so this is the union over its courses, deduped by profile page.
    const people = new Map();
    for (const course of members) {
      for (const person of course.instructors ?? []) {
        const page = person.page ?? person.slug ?? person.name;
        if (page && !people.has(page)) people.set(page, { name: person.name ?? page, page });
      }
    }

    let average = null;
    if (scored.length > 0) {
      average =
        reviews > 0
          ? scored.reduce(
              (total, course) => total + course.starisk * (course.reviews ?? 0),
              0,
            ) / reviews
          : scored.reduce((total, course) => total + course.starisk, 0) / scored.length;
    }

    programs.push({
      key,
      title: group.title ?? key,
      type: group.type ?? 'specialization',
      provider: group.provider ?? null,
      url: group.url ?? `https://www.coursera.org/${key}`,
      // The program page's own mark when there is a record; otherwise any member
      // course's, which is the same provider's logo. Programs have no image of
      // their own, so this is what a directory row can draw.
      image: scores[key]?.image ?? members.find((course) => course.image)?.image ?? null,
      courses: members.sort(
        (a, b) =>
          (b.starisk ?? -1) - (a.starisk ?? -1) ||
          (a.title ?? a.key).localeCompare(b.title ?? b.key),
      ),
      scored: scored.length,
      total: members.length,
      complete: members.length > 0 && scored.length === members.length,
      reviews,
      average,
      noReviews,
      unread,
      instructors: [...people.values()],
      low: scored.length ? Math.min(...scored.map((course) => course.starisk)) : null,
      high: scored.length ? Math.max(...scored.map((course) => course.starisk)) : null,
      coursera: typeof group.coursera === 'number' ? group.coursera : null,
      ratings: typeof group.ratings_total === 'number' ? group.ratings_total : null,
    });
  }

  return programs.sort(
    (a, b) =>
      (b.average ?? -1) - (a.average ?? -1) ||
      b.scored - a.scored ||
      a.title.localeCompare(b.title),
  );
}

/**
 * The other direction: which programs contain each course.
 *
 * Built once at build time and passed to the course page, so the relationship is
 * navigable both ways without shipping `groupings.json` to the browser. The
 * hash links back into the directory's drawer (`/programs#<program key>`).
 */
export function buildMemberships(groupings, scores) {
  const byCourse = new Map();

  for (const program of buildGroupings(groupings, scores)) {
    for (const course of program.courses) {
      const memberships = byCourse.get(course.key) ?? [];
      memberships.push({ key: program.key, title: program.title, type: program.type });
      byCourse.set(course.key, memberships);
    }
  }

  return byCourse;
}

/**
 * The lookup island's program payload: only the fields a result card and a
 * suggestion row draw. Keyed by program key, like the course lookup.
 */
export function buildProgramLookup(groupings, scores) {
  return Object.fromEntries(
    buildGroupings(groupings, scores).map((program) => [
      program.key,
      {
        key: program.key,
        title: program.title,
        type: program.type,
        label: typeLabel(program.type),
        provider: program.provider,
        total: program.total,
        scored: program.scored,
        average: program.average,
        reviews: program.reviews,
      },
    ]),
  );
}
