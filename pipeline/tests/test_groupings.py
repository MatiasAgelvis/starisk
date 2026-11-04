import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.cache import load_page, store_page
from starisk.groupings import (
    build_groupings,
    extract_grouping,
    fetch_missing,
    grouping_key,
    load_seed_keys,
)

PAGE = (
    '<meta property="og:title" content="Algorithms">'
    '<a href="/learn/algorithms-part1?specialization=algorithms" '
    'data-e2e="sdp-course-list-link">A</a>'
    '<a href="/learn/algorithms-part2?specialization=algorithms" '
    'data-e2e="sdp-course-list-link">B</a>'
    '<a href="/learn/algorithms-part1" data-e2e="sdp-course-list-link">A again</a>'
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

            keys = load_seed_keys(path)

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


if __name__ == "__main__":
    unittest.main()
