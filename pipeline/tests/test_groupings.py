import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.cache import load_page, store_page
from starisk.fetch import Retired
from starisk.groupings import (
    build_groupings,
    discover_candidates,
    extract_grouping,
    fetch_missing,
    grouping_key,
    load_seed_keys,
    read_index,
    read_seeds,
    refuse_reason,
    spread,
)

PAGE = (
    '<meta property="og:title" content="Algorithms">'
    '<a href="/learn/algorithms-part1?specialization=algorithms" '
    'data-e2e="sdp-course-list-link">A</a>'
    '<a href="/learn/algorithms-part2?specialization=algorithms" '
    'data-e2e="sdp-course-list-link">B</a>'
    '<a href="/learn/algorithms-part1" data-e2e="sdp-course-list-link">A again</a>'
)

# A program page has no written reviews, only Coursera's pooled rating.
RATED_PAGE = (
    '<meta property="og:title" content="Algorithms">'
    '<script type="application/ld+json">'
    '{"@type":"Product","name":"Algorithms",'
    '"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.7","ratingCount":3408}}'
    "</script>"
    '<a href="/learn/algorithms-part1" data-e2e="sdp-course-list-link">A</a>'
)


class GroupingKeyTest(unittest.TestCase):
    def test_specialization_and_professional_certificate_pages(self):
        self.assertEqual(
            grouping_key(Path("specializations__algorithms.html.gz")),
            "specializations/algorithms",
        )
        self.assertEqual(
            grouping_key(Path("professional-certificates__google-data-analytics.html.gz")),
            "professional-certificates/google-data-analytics",
        )

    def test_course_and_landing_pages_are_ignored(self):
        self.assertIsNone(grouping_key(Path("learn__algorithms-part1.html.gz")))
        self.assertIsNone(grouping_key(Path("learn__algorithms-part1.landing.html.gz")))
        self.assertEqual(
            grouping_key(Path("specializations__algorithms.landing.html.gz")),
            "specializations/algorithms",
        )
        self.assertIsNone(grouping_key(Path("specializations__algorithms.txt")))


class ExtractGroupingTest(unittest.TestCase):
    def test_reads_title_type_url_and_unique_courses(self):
        grouping = extract_grouping(PAGE, "specializations/algorithms")

        self.assertEqual(grouping["key"], "specializations/algorithms")
        self.assertEqual(grouping["type"], "specialization")
        self.assertEqual(grouping["title"], "Algorithms")
        self.assertEqual(
            grouping["url"], "https://www.coursera.org/specializations/algorithms"
        )
        self.assertEqual(
            grouping["courses"],
            ["learn/algorithms-part1", "learn/algorithms-part2"],
        )

    def test_professional_certificates_have_their_own_type(self):
        grouping = extract_grouping(PAGE, "professional-certificates/google-data-analytics")

        self.assertEqual(grouping["type"], "professional-certificate")

    def test_reads_the_bundle_rating_and_never_scores_the_program(self):
        grouping = extract_grouping(RATED_PAGE, "specializations/algorithms")

        self.assertEqual(grouping["coursera"], 4.7)
        self.assertEqual(grouping["ratings_total"], 3408)
        # The page's review widget belongs to one of its courses, so nothing that
        # looks like a score may come out of here.
        self.assertNotIn("starisk", grouping)
        self.assertNotIn("reviews", grouping)
        self.assertNotIn("top_review", grouping)

    def test_a_page_without_courses_is_not_a_program(self):
        self.assertIsNone(extract_grouping("<html></html>", "specializations/empty"))

    def test_boilerplate_titles_are_not_programs(self):
        html = (
            '<meta property="og:title" '
            'content="Coursera | Online Courses From Top Universities. Join for Free">'
            '<a href="/learn/a" data-e2e="sdp-course-list-link">A</a>'
        )

        self.assertIsNone(extract_grouping(html, "specializations/boilerplate"))


class BuildGroupingsTest(unittest.TestCase):
    def test_reads_only_program_pages_from_the_cache(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page("specializations/algorithms", PAGE, directory)
            store_page("learn/algorithms-part1", PAGE, directory)

            groupings = build_groupings(directory)

        self.assertEqual(list(groupings), ["specializations/algorithms"])
        self.assertEqual(len(groupings["specializations/algorithms"]["courses"]), 2)

    def test_falls_back_to_the_landing_copy(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # A specialization that is also a crawl source can have a boilerplate
            # base page and the real course list in its `.landing` copy.
            store_page("specializations/algorithms", "<html></html>", directory)
            store_page("specializations/algorithms.landing", PAGE, directory)

            groupings = build_groupings(directory)

        self.assertIn("specializations/algorithms", groupings)
        self.assertEqual(len(groupings["specializations/algorithms"]["courses"]), 2)


class SeedTest(unittest.TestCase):
    def test_load_seed_keys_filters_and_dedupes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "programs.json"
            path.write_text(
                json.dumps(
                    [
                        "professional-certificates/ibm-data-science",
                        "learn/not-a-program",
                        "specializations/algorithms",
                        "specializations/algorithms",
                        "bad",
                    ]
                ),
                encoding="utf-8",
            )

            keys = load_seed_keys(path, index_path=Path(tmp) / "missing.json")

        self.assertEqual(
            keys,
            ["professional-certificates/ibm-data-science", "specializations/algorithms"],
        )

    def test_published_programs_are_seeds_too(self):
        """A fresh clone has no cache: the index says which pages to fetch back."""
        with TemporaryDirectory() as tmp:
            seeds = Path(tmp) / "programs.json"
            seeds.write_text(json.dumps(["professional-certificates/ibm-data-science"]), encoding="utf-8")
            index = Path(tmp) / "groupings.json"
            index.write_text(
                json.dumps({"specializations/algorithms": {"key": "specializations/algorithms"}}),
                encoding="utf-8",
            )

            keys = load_seed_keys(seeds, index_path=index)

        self.assertEqual(
            keys,
            ["professional-certificates/ibm-data-science", "specializations/algorithms"],
        )

    def test_a_missing_seed_is_fetched_once(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return PAGE

        def failing(url):
            raise AssertionError("should not fetch a cached page")

        key = "professional-certificates/ibm-data-science"
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = fetch_missing([key], fetch=fetch, cache_dir=directory)
            second = fetch_missing([key], fetch=failing, cache_dir=directory)

            self.assertEqual(first, 1)
            self.assertEqual(second, 0)
            self.assertEqual(load_page(key, directory), PAGE)

        self.assertEqual(calls, [f"https://www.coursera.org/{key}"])

    def test_a_landing_copy_counts_as_cached(self):
        key = "professional-certificates/ibm-data-science"

        def failing(url):
            raise AssertionError("should not fetch a cached page")

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page(f"{key}.landing", PAGE, directory)

            self.assertEqual(fetch_missing([key], fetch=failing, cache_dir=directory), 0)


class RefuseReasonTest(unittest.TestCase):
    def test_an_empty_rebuild_over_a_full_index_is_refused(self):
        reason = refuse_reason({}, {"specializations/a": {}, "specializations/b": {}})

        self.assertIn("page cache", reason)
        self.assertIn("over 2", reason)

    def test_a_partial_rebuild_is_refused_too(self):
        reason = refuse_reason(
            {"specializations/a": {}},
            {"specializations/a": {}, "specializations/b": {}},
        )

        self.assertIsNotNone(reason)

    def test_the_same_index_is_written(self):
        index = {"specializations/a": {}}

        self.assertIsNone(refuse_reason(index, index))

    def test_growth_is_written(self):
        self.assertIsNone(refuse_reason({"a": {}, "b": {}}, {"a": {}}))

    def test_force_overrides(self):
        self.assertIsNone(refuse_reason({}, {"a": {}}, force=True))


class SpreadTest(unittest.TestCase):
    def test_is_a_permutation_and_ignores_the_input_order(self):
        slugs = [f"course-{index:03d}" for index in range(50)]

        spread_slugs = spread(slugs)

        self.assertEqual(sorted(spread_slugs), sorted(slugs))
        self.assertEqual(spread_slugs, spread(list(reversed(slugs))))

    def test_is_not_the_alphabetical_head(self):
        slugs = [f"course-{index:04d}" for index in range(1000)]

        first = spread(slugs)[:20]

        self.assertNotEqual(first, slugs[:20])
        # The first batch reaches well past the start of the alphabet.
        self.assertTrue(any(slugs.index(slug) >= 500 for slug in first))

    def test_a_new_slug_does_not_reorder_the_existing_ones(self):
        slugs = [f"course-{index:03d}" for index in range(100)]

        before = spread(slugs)
        after = spread([*slugs, "course-new"])

        self.assertEqual([slug for slug in after if slug in set(slugs)], before)


class DiscoverTest(unittest.TestCase):
    def test_walks_the_sitemap_and_skips_what_is_known(self):
        candidates = discover_candidates(
            {"specializations/known": {}},
            ["specializations/seeded"],
            {"specializations/dead": {}},
            ["known", "seeded", "dead", "fresh-a", "fresh-b"],
            limit=1,
        )

        self.assertEqual(candidates, ["specializations/fresh-a"])

    def test_an_exhausted_sitemap_yields_nothing(self):
        self.assertEqual(
            discover_candidates({"specializations/done": {}}, [], {}, ["done"], limit=5),
            [],
        )

    def test_a_cached_page_that_never_parsed_is_not_a_candidate(self):
        # Fetched, but with no course list to publish: not in the index, not a
        # seed, not retired. It must not sit at the head of the walk forever.
        candidates = discover_candidates(
            {},
            [],
            {},
            ["silent", "fresh"],
            limit=5,
            cached=["specializations/silent"],
        )

        self.assertEqual(candidates, ["specializations/fresh"])

    def test_reads_the_seed_list(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "programs.json"
            path.write_text('["specializations/a", " ", "professional-certificates/b"]')

            self.assertEqual(
                read_seeds(path),
                ["specializations/a", "professional-certificates/b"],
            )

    def test_a_missing_seed_file_is_empty_not_a_crash(self):
        self.assertEqual(read_seeds(Path("/nonexistent/programs.json")), [])


class FetchMissingTest(unittest.TestCase):
    def test_a_dead_program_page_is_tombstoned_once(self):
        calls = []
        retired = {}

        def fetch(url):
            calls.append(url)
            raise Retired(f"HTTP 404 for {url}")

        with TemporaryDirectory() as tmp:
            fetched = fetch_missing(
                ["specializations/dead", "specializations/dead"],
                fetch=fetch,
                cache_dir=Path(tmp) / "pages",
                retired=retired,
            )

        self.assertEqual(fetched, 0)
        self.assertIn("specializations/dead", retired)
        self.assertEqual(len(calls), 1)


class LoadSlugsTest(unittest.TestCase):
    def test_a_missing_file_is_an_empty_index(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(read_index(Path(tmp) / "groupings.json"), {})

    def test_a_broken_file_is_an_empty_index(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "groupings.json"
            path.write_text("{not json", encoding="utf-8")

            self.assertEqual(read_index(path), {})


if __name__ == "__main__":
    unittest.main()
