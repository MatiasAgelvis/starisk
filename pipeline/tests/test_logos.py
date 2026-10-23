import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.logos import localize_images, provider_slug, sniff_extension

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 32


class ProviderSlugTest(unittest.TestCase):
    def test_common_names(self):
        self.assertEqual(provider_slug("DeepLearning.AI"), "deeplearning-ai")
        self.assertEqual(provider_slug("Yale University"), "yale-university")
        self.assertEqual(provider_slug("  Google  "), "google")

    def test_accents_and_junk(self):
        self.assertEqual(provider_slug("École Polytechnique"), "ecole-polytechnique")
        self.assertEqual(provider_slug("University of Michigan & friends"), "university-of-michigan-friends")
        self.assertEqual(provider_slug(""), "provider")
        self.assertEqual(provider_slug("!!!"), "provider")

    def test_a_wild_name_cannot_become_a_900_char_filename(self):
        self.assertLessEqual(len(provider_slug("type-person-name-andrew-ng " * 40)), 64)


class SniffTest(unittest.TestCase):
    def test_known_formats(self):
        self.assertEqual(sniff_extension(PNG), ".png")
        self.assertEqual(sniff_extension(b"\xff\xd8\xff\xe0rest"), ".jpg")
        self.assertEqual(sniff_extension(WEBP), ".webp")
        self.assertEqual(sniff_extension(b"GIF89a...."), ".gif")
        self.assertEqual(sniff_extension(b'  <svg xmlns="...">'), ".svg")

    def test_unknown(self):
        self.assertIsNone(sniff_extension(b"<html>nope</html>"))
        self.assertIsNone(sniff_extension(b""))


class LocalizeTest(unittest.TestCase):
    def test_one_download_per_provider(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return PNG

        scores = {
            "learn/a": {"provider": "DeepLearning.AI", "image": "https://cdn/x.png"},
            "learn/b": {"provider": "DeepLearning.AI", "image": "https://cdn/x.png"},
            "learn/c": {"provider": "Yale University", "image": "https://cdn/y.png"},
        }
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            localize_images(scores, fetch=fake_fetch, out_dir=out, log=lambda *_: None)

            self.assertEqual(len(calls), 2)
            self.assertEqual(scores["learn/a"]["image"], "/logos/deeplearning-ai.png")
            self.assertEqual(scores["learn/b"]["image"], "/logos/deeplearning-ai.png")
            self.assertEqual(scores["learn/c"]["image"], "/logos/yale-university.png")
            self.assertTrue((out / "deeplearning-ai.png").exists())

    def test_second_run_makes_no_requests(self):
        def failing_fetch(url):
            raise AssertionError("should have reused the file")

        scores = {
            "learn/a": {"provider": "DeepLearning.AI", "image": "https://cdn/x.png"},
        }
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            localize_images(scores, fetch=lambda _: PNG, out_dir=out, log=lambda *_: None)
            localize_images(scores, fetch=failing_fetch, out_dir=out, log=lambda *_: None)

            self.assertEqual(scores["learn/a"]["image"], "/logos/deeplearning-ai.png")

    def test_failure_keeps_the_remote_url(self):
        def failing_fetch(url):
            raise RuntimeError("timeout")

        scores = {"learn/a": {"provider": "Yale University", "image": "https://cdn/y.png"}}
        with TemporaryDirectory() as tmp:
            localize_images(scores, fetch=failing_fetch, out_dir=Path(tmp), log=lambda *_: None)

            self.assertEqual(scores["learn/a"]["image"], "https://cdn/y.png")

    def test_unrecognised_bytes_keep_the_remote_url(self):
        scores = {"learn/a": {"provider": "Yale University", "image": "https://cdn/y.png"}}
        with TemporaryDirectory() as tmp:
            localize_images(scores, fetch=lambda _: b"<html>nope</html>", out_dir=Path(tmp), log=lambda *_: None)

            self.assertEqual(scores["learn/a"]["image"], "https://cdn/y.png")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_a_serialized_provider_is_not_a_filename(self):
        # An old crawl stored the JSON-LD person blob as the provider; the logo
        # file must fall back to a hash instead of Errno 63.
        scores = {
            "learn/a": {
                "provider": "[{'@type': 'Person', 'name': 'Andrew Ng'}]",
                "image": "https://cdn/x.png",
            }
        }
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            localize_images(scores, fetch=lambda _: PNG, out_dir=out, log=lambda *_: None)

            found = list(out.iterdir())
            self.assertEqual(len(found), 1)
            self.assertLessEqual(len(found[0].name), 64)
            self.assertTrue(scores["learn/a"]["image"].startswith("/logos/"))

    def test_local_and_missing_images_are_left_alone(self):
        scores = {
            "learn/a": {"provider": "Already Local", "image": "/logos/already-local.png"},
            "learn/b": {"provider": "No Image", "image": None},
            "learn/c": {"provider": "No Provider", "image": "https://cdn/z.png"},
        }
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            localize_images(scores, fetch=lambda _: PNG, out_dir=out, log=lambda *_: None)

            self.assertEqual(scores["learn/a"]["image"], "/logos/already-local.png")
            self.assertIsNone(scores["learn/b"]["image"])
            # No provider name: the file is named from the URL, still localized.
            self.assertTrue(scores["learn/c"]["image"].startswith("/logos/"))
            self.assertEqual(len(list(out.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
