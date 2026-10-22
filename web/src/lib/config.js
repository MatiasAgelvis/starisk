// Where "not indexed yet" sends a visitor.
//
// A `mailto:` with a prefilled subject/body, or a form URL (Tally, Formspree).
// While this is null the page just says the course isn't indexed — no dead
// link, and no developer-speak aimed at someone browsing Coursera.
//
// A GitHub issue tracker was the first idea and it was the wrong one: the
// audience here isn't developers, and an archived repo makes the link 404.
export const REQUEST_URL = null;

export function requestHref(key) {
  if (!REQUEST_URL) return null;

  if (REQUEST_URL.startsWith('mailto:')) {
    const subject = encodeURIComponent(`Course request: ${key}`);
    const body = encodeURIComponent(`Please score https://www.coursera.org/${key}`);
    return `${REQUEST_URL}?subject=${subject}&body=${body}`;
  }

  return `${REQUEST_URL}?course=${encodeURIComponent(key)}`;
}
