import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.cache import key_of, main, path_for, stats, store_page, verify

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"


class KeyTest(unittest.TestCase):
    def test_key_of_inverts_path_for(self):
        for key in ("learn/machine-learning", "learn/machine-learning.landing", "instructor/andrewng"):
            self.assertEqual(key_of(path_for(key, Path("/tmp"))), key)

    def test_an_underscore_in_a_slug_is_not_a_separator(self):
        self.assertEqual(key_of(Path("learn__a_b.html.gz")), "learn/a_b")


class StatsTest(unittest.TestCase):
    def test_counts_kinds_and_sizes_and_separates_landings(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store_page("learn/a", "<html>a</html>", directory)
            store_page("learn/a.landing", "<html>b</html>", directory)
            store_page("instructor/ada", "<html>c</html>", directory)
            store_page("specializations/s", "<html>d</html>", directory)

            data = stats(directory)

            self.assertEqual(data["pages"], 4)
            self.assertGreater(data["bytes"], 0)
            self.assertEqual(
                {kind: entry["pages"] for kind, entry in data["kinds"].items()},
                {
                    "instructor": 1,
                    "learn": 1,
                    "learn (landing)": 1,
                    "specializations": 1,
                },
            )
            self.assertIsNotNone(data["oldest"])
            self.assertIsNotNone(data["newest"])

    def test_a_missing_directory_is_empty_not_an_error(self):
        with TemporaryDirectory() as tmp:
            data = stats(Path(tmp) / "nope")
            self.assertEqual(data["pages"], 0)
            self.assertEqual(data["kinds"], {})
            self.assertIsNone(data["oldest"])


class VerifyTest(unittest.TestCase):
    def test_a_good_course_page_is_ok(self):
        html = FIXTURE.read_text(encoding="utf-8")
        with TemporaryDirectory() as tmp:
            store_page("learn/a", html, Path(tmp))
            data = verify(Path(tmp))

            self.assertEqual(data["counts"], {"learn": {"ok": 1}})
            self.assertEqual(data["failures"], [])

    def test_a_good_landing_page_is_ok(self):
        html = '<a href="/instructor/ada"><span>Ada Lovelace</span></a>'
        with TemporaryDirectory() as tmp:
            store_page("learn/a.landing", html, Path(tmp))
            data = verify(Path(tmp))

            self.assertEqual(data["counts"], {"learn (landing)": {"ok": 1}})

    def test_a_page_with_nothing_to_find_is_unparsed(self):
        with TemporaryDirectory() as tmp:
            store_page("learn/gone", "<html><body>nothing here</body></html>", Path(tmp))
            data = verify(Path(tmp))

            self.assertEqual(data["counts"], {"learn": {"unparsed": 1}})
            self.assertEqual(data["failures"][0]["status"], "unparsed")
            self.assertEqual(data["failures"][0]["key"], "learn/gone")

    def test_a_corrupt_file_is_unreadable(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path_for("learn/broken", directory).write_bytes(b"not gzip")
            data = verify(directory)

            self.assertEqual(data["counts"], {"learn": {"unreadable": 1}})

    def test_a_key_this_build_cannot_read_is_unknown(self):
        with TemporaryDirectory() as tmp:
            store_page("articles/x", "<html></html>", Path(tmp))
            data = verify(Path(tmp))

            self.assertEqual(data["counts"], {"articles": {"unknown": 1}})

    def test_json_output_is_valid_and_complete(self):
        with TemporaryDirectory() as tmp:
            store_page("learn/a", FIXTURE.read_text(encoding="utf-8"), Path(tmp))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["verify", "--directory", tmp, "--json"])

            self.assertEqual(code, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["counts"], {"learn": {"ok": 1}})
            self.assertEqual(data["failures"], [])


if __name__ == "__main__":
    unittest.main()
