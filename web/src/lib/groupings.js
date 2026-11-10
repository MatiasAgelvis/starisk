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
      low: scored.length ? Math.min(...scored.map((course) => course.starisk)) : null,
      high: scored.length ? Math.max(...scored.map((course) => course.starisk)) : null,
      programRating: typeof scores[key]?.starisk === 'number' ? scores[key].starisk : null,
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
