# Licensing

Starisk is three different things, and only two of them are ours to license.

## 1. Code — Apache-2.0

`pipeline/`, `web/src/`, `web/scripts/`, `ops/`, `.github/` and the build scripts
are licensed under Apache-2.0. See [LICENSE.txt](LICENSE.txt).

## 2. Measurements — CC BY 4.0

The numbers Starisk computes are ours: the Starisk score, spread, the gap
verdicts, program averages, and the shape of the corpus (titles, providers,
categories, program membership, Coursera's aggregate rating and rating counts).
Use them with attribution: **Starisk — https://starisk.matiasagelvis.com**.

## 3. Third-party content — not licensed here

`pipeline/data/scores.json` also carries material we do not own and cannot
relicense:

| Field | What it is | How it is used |
|---|---|---|
| `top_review` | A Coursera learner's written review, excerpted (≤ 1,200 characters) | Quoted, with a link to the original review page |
| `description` | The course's marketing copy (Coursera / the partner) | Shown on the course page to describe the course |
| `web/public/logos/*` | Providers' marks, trademarks of their owners | Identifying the provider |
| `instructors[].photo` | A URL to Coursera's CDN | Hotlinked; the image is never copied into this repository |

The published dataset is `/data/dataset.json` at
https://starisk.matiasagelvis.com. It carries the scores, counts and identifiers and
**none** of the prose or the marks above. `/data/scores.json` is the site's own
build input: it includes the quoted reviews, so it is a page feed, not the dataset.
