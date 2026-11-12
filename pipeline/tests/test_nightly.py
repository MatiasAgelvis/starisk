import unittest

from starisk import nightly

DATA = ["pipeline/data/scores.json"]


def record(score=4.2, reviews=20, **extra):
    return {"starisk": score, "reviews": reviews, **extra}


def corpus(**scores):
    return {f"learn/{name}": value for name, value in scores.items()}


class AllowedTest(unittest.TestCase):
    def test_data_files_are_allowed(self):
        self.assertTrue(nightly.allowed("pipeline/data/scores.json"))
        self.assertTrue(nightly.allowed("web/src/data/logo-sizes.json"))
        self.assertTrue(nightly.allowed("web/public/logos/tile/acme.png"))

    def test_code_is_not(self):
        self.assertFalse(nightly.allowed("pipeline/starisk/crawl.py"))
        self.assertFalse(nightly.allowed("web/src/pages/index.astro"))
        self.assertFalse(nightly.allowed("TODO.md"))


class DiffSummaryTest(unittest.TestCase):
    def test_counts_records_both_ways(self):
        before = corpus(a=record(), b=record(), gone=record())
        after = corpus(a=record(score=4.5), b=record(), fresh=record())

        summary = nightly.diff_summary(before, after)

        self.assertEqual(summary["added"], ["learn/fresh"])
        self.assertEqual(summary["removed"], ["learn/gone"])
        self.assertEqual(summary["updated"], ["learn/a"])
        self.assertEqual(summary["scored"], 3)
        self.assertEqual(summary["scored_before"], 3)

    def test_untouched_records_are_not_updated(self):
        before = corpus(a=record())
        summary = nightly.diff_summary(before, corpus(a=record()))

        self.assertEqual(summary["updated"], [])


class DecideTest(unittest.TestCase):
    def setUp(self):
        self.before = corpus(a=record(), b=record())
        self.before_stats = nightly.crawl.summarize(self.before)

    def decide(self, after, changed=None, adapter_ok=True):
        summary = nightly.diff_summary(self.before, after)
        return nightly.decide(
            DATA if changed is None else changed,
            summary,
            self.before_stats,
            adapter_ok=adapter_ok,
        )

    def test_a_clean_run_commits(self):
        decision = self.decide(corpus(a=record(), b=record(score=4.4)))

        self.assertEqual(decision.code, nightly.OK)
        self.assertTrue(decision.commit)

    def test_a_broken_adapter_does_not_commit(self):
        decision = self.decide(corpus(a=record()), adapter_ok=False)

        self.assertEqual(decision.code, nightly.SMOKE)
        self.assertFalse(decision.commit)

    def test_code_changes_are_refused(self):
        decision = self.decide(corpus(a=record()), changed=DATA + ["web/src/pages/index.astro"])

        self.assertEqual(decision.code, nightly.GATE)
        self.assertFalse(decision.commit)

    def test_nothing_changed_is_not_a_commit(self):
        decision = self.decide(corpus(a=record(), b=record()), changed=[])

        self.assertEqual(decision.code, nightly.NOTHING)
        self.assertFalse(decision.commit)

    def test_disappearing_records_are_refused(self):
        decision = self.decide(corpus(a=record()))

        self.assertEqual(decision.code, nightly.GATE)
        self.assertIn("disappeared", decision.reason)

    def test_a_score_drop_is_refused(self):
        before = {f"learn/{index}": record() for index in range(10)}
        after = {
            **{f"learn/{index}": {"no_reviews": True} for index in range(7)},
            **{f"learn/{index}": record() for index in range(7, 10)},
        }

        decision = nightly.decide(
            DATA,
            nightly.diff_summary(before, after),
            nightly.crawl.summarize(before),
        )

        self.assertEqual(decision.code, nightly.GATE)
        self.assertIn("dropped", decision.reason)

    def test_error_growth_is_refused(self):
        after = corpus(
            a=record(),
            b=record(error="fetch: timeout"),
            c=record(error="fetch: x"),
            d=record(error="fetch: y"),
        )

        decision = self.decide(after)

        self.assertEqual(decision.code, nightly.GATE)
        self.assertIn("errors", decision.reason)

    def test_a_rate_limited_run_is_partial_not_refused(self):
        after = corpus(a=record(), b=record(landing_error="rate limited: 429"))

        decision = self.decide(after)

        self.assertEqual(decision.code, nightly.PARTIAL)
        self.assertTrue(decision.commit)


class MessageTest(unittest.TestCase):
    def summary(self, added=0, updated=0):
        return {
            "added": [f"learn/new{i}" for i in range(added)],
            "updated": [f"learn/old{i}" for i in range(updated)],
            "scored": 800,
            "scored_before": 790,
            "errors": 0,
            "rate_limited": False,
        }

    def test_add_and_rescore(self):
        self.assertEqual(
            nightly.commit_message(self.summary(added=26, updated=7)),
            "data(crawl): add 26 courses, rescore 7",
        )

    def test_one_course_is_singular(self):
        self.assertEqual(
            nightly.commit_message(self.summary(added=1)), "data(crawl): add 1 course"
        )

    def test_rescore_only(self):
        self.assertEqual(
            nightly.commit_message(self.summary(updated=3)),
            "data(crawl): rescore 3 courses",
        )

    def test_fallback_when_only_metadata_moved(self):
        self.assertEqual(
            nightly.commit_message(self.summary()), "data(crawl): refresh course data"
        )

    def test_the_body_reports_the_delta(self):
        body = nightly.commit_body(self.summary(added=10, updated=2), nightly.Decision(nightly.OK, "committed"))

        self.assertIn("800 scored (+10), 2 rescored", body)

    def test_a_partial_run_says_so(self):
        body = nightly.commit_body(
            self.summary(added=1), nightly.Decision(nightly.PARTIAL, "Coursera rate-limited the crawl")
        )

        self.assertIn("Partial run", body)

    def test_the_pr_body_names_the_day_and_the_state(self):
        body = nightly.pr_body(self.summary(added=4), nightly.Decision(nightly.OK, "committed"), "2026-11-13")

        self.assertIn("2026-11-13", body)
        self.assertIn("committed", body)


if __name__ == "__main__":
    unittest.main()
