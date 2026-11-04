import io
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from unittest import mock

from starisk.fetch import RateLimited, _wait_seconds, fetch_page

URL = "https://www.coursera.org/learn/x/reviews"


class FakeResponse:
    """The context-manager surface `urlopen` returns."""

    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError(URL, code, "error", message, io.BytesIO(b""))


class RateLimitTest(unittest.TestCase):
    def test_a_429_stops_without_retrying(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            raise http_error(429)

        with (
            mock.patch("starisk.fetch.urllib.request.urlopen", fake_urlopen),
            mock.patch("starisk.fetch.time.sleep") as sleep,
            self.assertRaises(RateLimited),
        ):
            fetch_page(URL, retries=2)

        self.assertEqual(calls, [URL])
        sleep.assert_not_called()

    def test_a_403_stops_without_retrying(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            raise http_error(403)

        with (
            mock.patch("starisk.fetch.urllib.request.urlopen", fake_urlopen),
            mock.patch("starisk.fetch.time.sleep") as sleep,
            self.assertRaises(RateLimited),
        ):
            fetch_page(URL, retries=2)

        self.assertEqual(calls, [URL])
        sleep.assert_not_called()


class RetryTest(unittest.TestCase):
    def test_a_404_is_fatal_and_not_retried(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            raise http_error(404)

        with (
            mock.patch("starisk.fetch.urllib.request.urlopen", fake_urlopen),
            self.assertRaises(RuntimeError),
        ):
            fetch_page(URL, retries=2)

        self.assertEqual(calls, [URL])

    def test_transient_network_errors_are_retried(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            if len(calls) < 3:
                raise urllib.error.URLError("temporary")
            return FakeResponse(b"<html>ok</html>")

        with (
            mock.patch("starisk.fetch.urllib.request.urlopen", fake_urlopen),
            mock.patch("starisk.fetch.time.sleep"),
        ):
            body = fetch_page(URL, retries=2, backoff=0)

        self.assertEqual(body, "<html>ok</html>")
        self.assertEqual(len(calls), 3)

    def test_exhausted_retries_raise(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            raise urllib.error.URLError("down")

        with (
            mock.patch("starisk.fetch.urllib.request.urlopen", fake_urlopen),
            mock.patch("starisk.fetch.time.sleep"),
            self.assertRaises(RuntimeError),
        ):
            fetch_page(URL, retries=2, backoff=0)

        self.assertEqual(len(calls), 3)


class BackoffTest(unittest.TestCase):
    def test_retry_after_seconds_is_honoured(self):
        self.assertEqual(_wait_seconds(http_error(429, {"Retry-After": "7"}), 0, 2.0), 7.0)

    def test_a_non_numeric_retry_after_falls_back_to_jittered_backoff(self):
        wait = _wait_seconds(http_error(429, {"Retry-After": "not-a-date"}), 1, 2.0)

        self.assertGreaterEqual(wait, 4.0)
        self.assertLessEqual(wait, 5.2)

    def test_retry_after_http_date_is_honoured(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=30)
        header = format_datetime(when, usegmt=True)

        wait = _wait_seconds(http_error(429, {"Retry-After": header}), 0, 2.0)

        self.assertGreaterEqual(wait, 25.0)
        self.assertLessEqual(wait, 30.0)

    def test_a_past_http_date_waits_at_least_one_second(self):
        when = datetime.now(timezone.utc) - timedelta(seconds=30)
        header = format_datetime(when, usegmt=True)

        self.assertEqual(_wait_seconds(http_error(429, {"Retry-After": header}), 0, 2.0), 1.0)


if __name__ == "__main__":
    unittest.main()
