import unittest
from datetime import datetime, timezone
from pathlib import Path

from starisk.crawl import crawl, normalize_source, reviews_url, score_page

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

        self.assertEqual(slept, [1.5, 1.5, 1.5])


if __name__ == "__main__":
    unittest.main()
