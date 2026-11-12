import unittest
from pathlib import Path

from starisk import smoke

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"


class FakeResponse:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener(status=200, headers=None):
    return lambda request, timeout=0: FakeResponse(status, headers or {})


class CourseCheckTest(unittest.TestCase):
    def test_a_parsing_page_reports_nothing(self):
        html = FIXTURE.read_text(encoding="utf-8")

        self.assertEqual(smoke.check_course(fetch=lambda url: html), [])

    def test_a_page_without_reviews_is_reported(self):
        problems = smoke.check_course(fetch=lambda url: "")

        self.assertEqual(len(problems), 1)
        self.assertIn("no reviews parsed", problems[0].detail)

    def test_a_failed_fetch_is_reported_not_raised(self):
        def fetch(url):
            raise OSError("connection reset")

        problems = smoke.check_course(fetch=fetch)

        self.assertIn("fetch failed", problems[0].detail)


class SiteCheckTest(unittest.TestCase):
    HEADERS = {
        "access-control-allow-origin": "*",
        "content-length": str(3_000_000),
    }

    def test_a_healthy_deployment_reports_nothing(self):
        self.assertEqual(smoke.check_site(opener=opener(headers=self.HEADERS)), [])

    def test_a_missing_cors_header_is_a_problem(self):
        problems = smoke.check_site(
            opener=opener(headers={"content-length": str(3_000_000)})
        )

        self.assertIn("CORS", problems[0].detail)

    def test_a_tiny_file_is_a_problem(self):
        problems = smoke.check_site(
            opener=opener(headers={**self.HEADERS, "content-length": "20"})
        )

        self.assertIn("bytes", problems[0].detail)

    def test_the_unreachable_site_is_a_problem(self):
        def fail(request, timeout=0):
            raise OSError("dns")

        problems = smoke.check_site(opener=fail)

        self.assertIn("dns", problems[0].detail)


class ReportTest(unittest.TestCase):
    def test_site_problems_do_not_gate_the_run(self):
        report = smoke.Report(adapter=[], site=[smoke.Problem("site", "stale deploy")])

        self.assertTrue(report.ok)

    def test_adapter_problems_gate_the_run(self):
        report = smoke.Report(adapter=[smoke.Problem("reviews", "no reviews parsed")])

        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
