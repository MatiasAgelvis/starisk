import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.cache import store_page
from starisk.logo_hires import header_logo_url, hires_url, localize_hires

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

PAGE = (
    '<div><p>Some course</p>'
    '<img src="https://d3njjcbhbojbot.cloudfront.net/api/utilities/v1/imageproxy/'
    'https://coursera-university-assets.s3.amazonaws.com/aa/bb/logo.png'
    '?auto=format%2Ccompress&amp;dpr=1" alt=""/></div>'
)


class HeaderLogoTest(unittest.TestCase):
    def test_finds_the_partner_mark(self):
        url = header_logo_url(PAGE)
        self.assertIsNotNone(url)
        self.assertIn("coursera-university-assets", url)
        # The HTML entity is decoded, or the request would ask for `&amp;dpr`.
        self.assertNotIn("&amp;", url)

    def test_missing(self):
        self.assertIsNone(header_logo_url("<img src='https://example.com/x.png'/>"))

    def test_ignores_the_json_ld_thumbnail(self):
        # `product.image` is the 160x60 lockup; only the header `<img>` is the big one.
        page = '{"image":"https://cdn/small.png"}' + PAGE
        self.assertIn("coursera-university-assets", header_logo_url(page))


class HiresUrlTest(unittest.TestCase):
    def test_asks_for_the_requested_size(self):
        url = "https://proxy/imageproxy/https://assets/logo.png?auto=format%2Ccompress&dpr=1"
        self.assertTrue(hires_url(url, 1).endswith("dpr=1"))
        self.assertTrue(hires_url(url, 2).endswith("dpr=2"))

    def test_adds_a_query_when_there_is_none(self):
        self.assertTrue(hires_url("https://proxy/imageproxy/https://assets/logo.png").endswith("dpr=2"))


class LocalizeHiresTest(unittest.TestCase):
    def scores(self):
        return {
            "learn/a": {"provider": "Yale University", "image": "/logos/yale-university.png"},
            "learn/b": {"provider": "Yale University", "image": "/logos/yale-university.png"},
            "learn/c": {"provider": "Duke University", "image": "/logos/duke-university.png"},
        }

    def test_one_download_per_size_per_provider(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return PNG

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, out = root / "cache", root / "out"
            store_page("learn/a", PAGE, cache)

            mapping = localize_hires(
                self.scores(), cache_dir=cache, out_dir=out, fetch=fake_fetch, log=lambda *_: None
            )

            # Two sizes for Yale; Duke has no cached page, so it is left out.
            self.assertEqual(len(calls), 2)
            self.assertEqual(
                sorted(call.split("dpr=")[-1] for call in calls), ["1", "2"]
            )
            self.assertEqual(
                mapping,
                {
                    "/logos/yale-university.png": {
                        "tile": "/logos/tile/yale-university.png",
                        "full": "/logos/full/yale-university.png",
                    }
                },
            )
            self.assertTrue((out / "tile" / "yale-university.png").exists())
            self.assertTrue((out / "full" / "yale-university.png").exists())
            self.assertEqual(list(out.rglob("*.tmp")), [])

    def test_second_run_makes_no_requests(self):
        def failing_fetch(url):
            raise AssertionError("should have reused the files")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, out = root / "cache", root / "out"
            store_page("learn/a", PAGE, cache)
            first = localize_hires(
                self.scores(), cache_dir=cache, out_dir=out, fetch=lambda _: PNG, log=lambda *_: None
            )
            second = localize_hires(
                self.scores(), cache_dir=cache, out_dir=out, fetch=failing_fetch, log=lambda *_: None
            )
            self.assertEqual(first, second)

    def test_a_provider_without_a_cached_page_is_left_out(self):
        # No mapping means the page falls back to the small mark.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = localize_hires(
                self.scores(),
                cache_dir=root / "cache",
                out_dir=root / "out",
                fetch=lambda _: PNG,
                log=lambda *_: None,
            )
            self.assertEqual(mapping, {})

    def test_a_failed_download_is_not_mapped(self):
        def broken_fetch(url):
            raise OSError("network down")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, out = root / "cache", root / "out"
            store_page("learn/a", PAGE, cache)
            mapping = localize_hires(
                self.scores(), cache_dir=cache, out_dir=out, fetch=broken_fetch, log=lambda *_: None
            )
            self.assertEqual(mapping, {})

    def test_one_size_can_survive_the_other_failing(self):
        def flaky_fetch(url):
            if url.endswith("dpr=2"):
                raise OSError("boom")
            return PNG

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, out = root / "cache", root / "out"
            store_page("learn/a", PAGE, cache)
            mapping = localize_hires(
                self.scores(), cache_dir=cache, out_dir=out, fetch=flaky_fetch, log=lambda *_: None
            )
            self.assertEqual(
                mapping, {"/logos/yale-university.png": {"tile": "/logos/tile/yale-university.png"}}
            )

    def test_ignores_paths_that_are_not_localized_logos(self):
        scores = {"learn/a": {"provider": "Yale University", "image": "https://cdn/yale.png"}}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_page("learn/a", PAGE, root / "cache")
            mapping = localize_hires(
                scores,
                cache_dir=root / "cache",
                out_dir=root / "out",
                fetch=lambda _: PNG,
                log=lambda *_: None,
            )
            self.assertEqual(mapping, {})
