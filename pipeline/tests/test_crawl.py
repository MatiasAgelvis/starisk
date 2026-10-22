import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.cache import load_page, path_for, store_page
from starisk.crawl import (
    crawl,
    excerpt,
    is_fresh,
    normalize_source,
    order_by_staleness,
    parse_args,
    reviews_url,
    score_page,
    unique_sources,
)
from starisk.fetch import RateLimited

GOOD_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"
STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


class ScorePageTest(unittest.TestCase):
    def test_scores_a_good_page(self):
        result = score_page(GOOD_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(result)
        self.assertEqual(result["reviews"], 3)
        self.assertEqual(result["model"], "simple")
        self.assertEqual(result["title"], "Sample Course")
        self.assertEqual(result["provider"], "Test University")
        self.assertEqual(result["starisk"], 1.5)
        self.assertAlmostEqual(result["coursera"], 4.9)
        self.assertEqual(result["top_review"]["likes"], 80)
        self.assertEqual(result["top_review"]["stars"], 1.0)
        self.assertIn("rushed", result["top_review"]["text"])

    def test_returns_none_when_there_are_no_reviews(self):
        self.assertIsNone(score_page("<html><body>nothing</body></html>"))

    def test_records_the_population_and_the_spread(self):
        result = score_page(GOOD_FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(result["reviews_total"], 6214)
        self.assertNotIn("ratings_total", result)  # the fixture has no ratingCount
        self.assertIsInstance(result["spread"], float)
        self.assertGreaterEqual(result["spread"], 0.0)
        self.assertIsInstance(result["spread_weighted"], float)
        self.assertNotIn("level", result)
        self.assertNotIn("enrollment", result)


class CrawlTest(unittest.TestCase):
    def setUp(self):
        self.good_html = GOOD_FIXTURE.read_text(encoding="utf-8")

    def test_builds_the_reviews_url(self):
        self.assertEqual(
            reviews_url("learn/machine-learning"),
            "https://www.coursera.org/learn/machine-learning/reviews",
        )
        self.assertEqual(
            reviews_url("/learn/machine-learning/"),
            "https://www.coursera.org/learn/machine-learning/reviews",
        )

    def test_normalizes_full_coursera_urls(self):
        expected = "learn/machine-learning"
        self.assertEqual(normalize_source("learn/machine-learning"), expected)
        self.assertEqual(normalize_source("/learn/machine-learning/"), expected)
        self.assertEqual(
            normalize_source("https://www.coursera.org/learn/machine-learning"), expected
        )
        self.assertEqual(
            normalize_source("https://www.coursera.org/learn/machine-learning/reviews?page=2"),
            expected,
        )

    def test_scores_successes_and_records_errors(self):
        def fake_fetch(url):
            if "good" in url:
                return self.good_html
            if "broken" in url:
                raise RuntimeError("boom")
            return "<html></html>"  # fetched, but no reviews

        scores = crawl(
            ["learn/good", "learn/broken", "learn/empty"],
            fetch=fake_fetch,
            delay=0,
            now=STAMP,
            sleep=lambda _: None,
        )

        self.assertIn("starisk", scores["learn/good"])
        self.assertEqual(scores["learn/good"]["scrapedAt"], STAMP.isoformat())
        self.assertIn("error", scores["learn/broken"])
        self.assertIn("error", scores["learn/empty"])

    def test_failed_parse_does_not_overwrite_a_good_record(self):
        existing = {
            "learn/good": {"starisk": 4.2, "reviews": 10, "scrapedAt": "old"}
        }

        scores = crawl(
            ["learn/good"],
            fetch=lambda url: "<html></html>",
            existing=existing,
            now=STAMP,
            sleep=lambda _: None,
        )

        self.assertEqual(scores["learn/good"]["starisk"], 4.2)
        self.assertEqual(scores["learn/good"]["scrapedAt"], "old")
        self.assertIn("error", scores["learn/good"])

    def test_throttles_between_requests(self):
        slept = []

        crawl(
            ["learn/a", "learn/b", "learn/c"],
            fetch=lambda url: self.good_html,
            delay=1.5,
            now=STAMP,
            sleep=slept.append,
        )

        self.assertEqual(slept, [1.5] * 6)  # two requests per course, each throttled


class SourceListTest(unittest.TestCase):
    def test_variants_collapse_to_one_course(self):
        sources = [
            "learn/machine-learning",
            "https://www.coursera.org/learn/machine-learning",
            "/learn/machine-learning/",
            "machine-learning",
        ]
        self.assertEqual(unique_sources(sources), ["learn/machine-learning"])

    def test_bare_slug_gets_a_type(self):
        self.assertEqual(normalize_source("machine-learning"), "learn/machine-learning")

    def test_stalest_first_never_scraped_before_old(self):
        scores = {
            "learn/a": {"starisk": 1.0, "scrapedAt": "2026-03-01T00:00:00+00:00"},
            "learn/b": {"starisk": 1.0, "scrapedAt": "2025-01-01T00:00:00+00:00"},
        }
        self.assertEqual(
            order_by_staleness(["learn/a", "learn/c", "learn/b"], scores),
            ["learn/c", "learn/b", "learn/a"],
        )


class FreshnessTest(unittest.TestCase):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_recent_is_fresh(self):
        record = {"starisk": 3.0, "scrapedAt": "2026-05-20T00:00:00+00:00"}
        self.assertTrue(is_fresh(record, self.now, 30))

    def test_old_is_stale(self):
        record = {"starisk": 3.0, "scrapedAt": "2026-01-01T00:00:00+00:00"}
        self.assertFalse(is_fresh(record, self.now, 30))

    def test_failures_are_never_fresh(self):
        self.assertFalse(is_fresh({"error": "fetch: HTTP 404"}, self.now, 30))
        self.assertFalse(is_fresh({"starisk": 3.0}, self.now, 30))
        self.assertFalse(is_fresh(None, self.now, 30))

    def test_zero_max_age_is_always_stale(self):
        record = {"starisk": 3.0, "scrapedAt": self.now.isoformat()}
        self.assertFalse(is_fresh(record, self.now, 0))


class IncrementalCrawlTest(unittest.TestCase):
    def setUp(self):
        self.html = GOOD_FIXTURE.read_text(encoding="utf-8")

    def test_fresh_records_are_not_fetched(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return self.html

        existing = {"learn/fresh": {"starisk": 3.0, "scrapedAt": STAMP.isoformat()}}
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)

        crawl(["learn/fresh", "learn/new"], fetch=fetch, existing=existing, now=now, max_age_days=30)

        self.assertEqual([u for u in calls if u.endswith("/reviews")], [reviews_url("learn/new")])

    def test_limit_only_fetches_what_it_was_allowed(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return self.html

        crawl(["learn/a", "learn/b", "learn/c"], fetch=fetch, now=STAMP, limit=2)

        self.assertEqual(
            [u for u in calls if u.endswith("/reviews")],
            [reviews_url("learn/a"), reviews_url("learn/b")],
        )

    def test_rate_limit_stops_the_run_and_keeps_progress(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if url == reviews_url("learn/b"):
                raise RateLimited("HTTP 429")
            return self.html

        scores = crawl(["learn/a", "learn/b", "learn/c"], fetch=fetch, now=STAMP)

        self.assertIn("learn/a", scores)
        self.assertTrue(str(scores["learn/b"]["error"]).startswith("rate limited"))
        self.assertNotIn("learn/c", scores)
        self.assertFalse(any("learn/c" in url for url in calls))


class ArgsTest(unittest.TestCase):
    def test_defaults(self):
        options = parse_args([])

        self.assertEqual(options["max_age"], 30.0)
        self.assertIsNone(options["limit"])
        self.assertIsNone(options["sources"])

    def test_flags(self):
        options = parse_args(["--delay", "3", "--max-age", "7", "--limit", "10", "learn/x"])

        self.assertEqual(options["delay"], 3.0)
        self.assertEqual(options["max_age"], 7.0)
        self.assertEqual(options["limit"], 10)
        self.assertEqual(options["sources"], ["learn/x"])

    def test_force_means_everything_is_stale(self):
        self.assertEqual(parse_args(["--force"])["max_age"], 0.0)


    def test_landing_page_adds_instructors_and_categories(self):
        reviews = GOOD_FIXTURE.read_text(encoding="utf-8")
        landing = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"Sample",'
            '"instructor":{"name":"Andrew Ng"}}'
            "</script>"
            '"domains":[{"domainName":"Data Science","subdomainId":"ml",'
            '"subdomainName":"Machine Learning"}]'
        )

        def fetch(url):
            return landing if url.endswith("/learn/a") else reviews

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            scores = crawl(["learn/a"], fetch=fetch, now=STAMP, cache_dir=directory)

            self.assertEqual(scores["learn/a"]["instructors"], ["Andrew Ng"])
            self.assertEqual(scores["learn/a"]["categories"], ["Data Science"])
            self.assertTrue(path_for("learn/a.landing", directory).exists())

    def test_a_failed_landing_page_does_not_fail_the_course(self):
        reviews = GOOD_FIXTURE.read_text(encoding="utf-8")

        def fetch(url):
            if url.endswith("/learn/a"):
                raise RuntimeError("HTTP 404")
            return reviews

        with TemporaryDirectory() as tmp:
            scores = crawl(["learn/a"], fetch=fetch, now=STAMP, cache_dir=Path(tmp))

        self.assertEqual(scores["learn/a"]["starisk"], 1.5)
        self.assertNotIn("instructors", scores["learn/a"])


class CacheTest(unittest.TestCase):
    def test_roundtrip(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page("learn/a", "<html>hello</html>", directory)

            self.assertEqual(load_page("learn/a", directory), "<html>hello</html>")
            self.assertTrue(path_for("learn/a", directory).name.startswith("learn__a"))

    def test_missing_page_is_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(load_page("learn/gone", Path(tmp)))

    def test_crawl_stores_what_it_fetches(self):
        html = GOOD_FIXTURE.read_text(encoding="utf-8")
        with TemporaryDirectory() as tmp:
            crawl(["learn/a"], fetch=lambda _: html, now=STAMP, cache_dir=Path(tmp))
            self.assertEqual(load_page("learn/a", Path(tmp)), html)

    def test_offline_crawl_makes_no_requests(self):
        html = GOOD_FIXTURE.read_text(encoding="utf-8")
        calls = []

        def fetch(url):
            calls.append(url)
            return html

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page("learn/a", html, directory)

            scores = crawl(["learn/a"], fetch=fetch, now=STAMP, offline=True, cache_dir=directory)

        self.assertEqual(calls, [])
        self.assertEqual(scores["learn/a"]["starisk"], 1.5)

    def test_offline_keeps_the_original_stamp(self):
        html = GOOD_FIXTURE.read_text(encoding="utf-8")
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page("learn/a", html, directory)
            existing = {"learn/a": {"starisk": 9.9, "scrapedAt": "2026-01-01T00:00:00+00:00"}}

            scores = crawl(
                ["learn/a"], existing=existing, now=STAMP, offline=True, cache_dir=directory
            )

        # Re-parsed, but not re-scraped: the date must survive.
        self.assertEqual(scores["learn/a"]["starisk"], 1.5)
        self.assertEqual(scores["learn/a"]["scrapedAt"], "2026-01-01T00:00:00+00:00")

    def test_offline_missing_cache_leaves_a_good_record_alone(self):
        with TemporaryDirectory() as tmp:
            existing = {"learn/a": {"starisk": 3.3, "scrapedAt": "2026-01-01T00:00:00+00:00"}}

            scores = crawl(
                ["learn/a"], existing=existing, now=STAMP, offline=True, cache_dir=Path(tmp)
            )

        self.assertEqual(scores["learn/a"]["starisk"], 3.3)
        self.assertNotIn("error", scores["learn/a"])

    def test_offline_without_a_cached_page_records_an_error(self):
        with TemporaryDirectory() as tmp:
            scores = crawl(["learn/a"], now=STAMP, offline=True, cache_dir=Path(tmp))

        self.assertIn("offline", scores["learn/a"]["error"])


class ExcerptTest(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(excerpt("A short review."), "A short review.")

    def test_prefers_a_sentence_end(self):
        text = "A" * 120 + ". " + "B" * 200
        result = excerpt(text, limit=200)

        self.assertTrue(result.endswith(". …"))
        self.assertLessEqual(len(result), 125)

    def test_never_ends_mid_word(self):
        text = "word " * 200
        result = excerpt(text.strip(), limit=100)

        self.assertTrue(result.endswith("word…"))
        self.assertNotIn("wor …", result)

    def test_collapses_whitespace(self):
        self.assertEqual(excerpt("a\n\nb   c"), "a b c")

    def test_empty(self):
        self.assertEqual(excerpt(""), "")
        self.assertEqual(excerpt(None), "")


if __name__ == "__main__":
    unittest.main()
