// Instructors are not a crawl unit — they are a *view* of the course records.
// A teacher's catalogue average weights each course by the reviews actually read,
// because a 19-review course should not pull as hard as a 20-review one... which
// is to say: it barely weights anything, and the page says so. That is the point:
// with 1–5 courses per teacher, the catalogue average is a conversation starter,
// not a rating.
//
// Co-teaching is counted for everyone listed. Martha White and Adam White teach
// the same four courses, so their pages are identical; that is honest, and the
// page says so rather than inventing a way to split a shared course.

const PERSON_FIELDS = ['name', 'slug', 'url', 'id', 'role', 'department', 'learners', 'courses_taught', 'photo'];

/**
 * Collapse every course record into one entry per person.
 * @returns an array sorted for the directory: most courses first.
 */
export function buildInstructors(scores) {
  const people = new Map();

  for (const [key, record] of Object.entries(scores)) {
    if (typeof record.starisk !== 'number') continue;

    const team = record.instructors ?? [];
    for (const person of team) {
      const page = person.page ?? person.slug ?? person.name;
      let entry = people.get(page);

      if (!entry) {
        entry = { page, courses: [] };
        for (const field of PERSON_FIELDS) entry[field] = person[field] ?? null;
        people.set(page, entry);
      } else {
        // The same person arrives once per course; take the first non-empty
        // value for each field rather than letting a later page blank it.
        for (const field of PERSON_FIELDS) {
          if (entry[field] == null && person[field] != null) entry[field] = person[field];
        }
      }

      entry.courses.push({
        key,
        title: record.title ?? key,
        provider: record.provider ?? null,
        image: record.image ?? null,
        coursera: record.coursera ?? null,
        starisk: record.starisk,
        reviews: record.reviews ?? 0,
        co: team
          .filter((other) => (other.page ?? other.slug ?? other.name) !== page)
          .map((other) => ({
            name: other.name,
            page: other.page ?? other.slug ?? other.name,
          })),
      });
    }
  }

  for (const entry of people.values()) {
    const weight = entry.courses.reduce((total, course) => total + course.reviews, 0);
    entry.reviews = weight;
    entry.average =
      weight > 0
        ? entry.courses.reduce((total, course) => total + course.starisk * course.reviews, 0) / weight
        : entry.courses.reduce((total, course) => total + course.starisk, 0) / entry.courses.length;
    entry.low = Math.min(...entry.courses.map((course) => course.starisk));
    entry.high = Math.max(...entry.courses.map((course) => course.starisk));
    entry.courses.sort((a, b) => b.starisk - a.starisk || a.title.localeCompare(b.title));
  }

  return [...people.values()].sort(
    (a, b) =>
      b.courses.length - a.courses.length ||
      b.average - a.average ||
      (a.name ?? a.page).localeCompare(b.name ?? b.page),
  );
}

/** The lookup island matches a pasted Coursera profile URL to our page. */
export function teacherIndex(instructors) {
  return Object.fromEntries(
    instructors
      .filter((person) => person.slug)
      .map((person) => [person.slug, { page: person.page, name: person.name ?? person.page }]),
  );
}

/** "Dr. Barbara Oakley" -> "BO": two letters behind a missing or broken photo. */
export function initials(name) {
  const words = (name ?? '')
    .replace(/^(?:prof\.?|dr\.?|mr\.?|ms\.?|mrs\.?)\s+/i, '')
    .replace(/,?\s+(?:ph\.?\s?d\.?|m\.?\s?d\.?)$/i, '')
    .split(/\s+/)
    .filter((word) => /^[A-Za-z]/.test(word));

  if (words.length === 0) return '';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
