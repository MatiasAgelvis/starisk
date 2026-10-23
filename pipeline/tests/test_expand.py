import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.expand import bare_title, indexed_instructors, load_slugs, plan, resolve_specialization


def og(title: str) -> str:
    return f'<meta data-rh="true" property="og:title" content="{title}"/>'


class BareTitleTest(unittest.TestCase):
    def test_drops_the_word_specialization(self):
        self.assertEqual(bare_title("Deep Learning Specialization"), "Deep Learning")

    def test_keeps_honors_handling(self):
        self.assertEqual(
            bare_title("Financial Markets (with Honors)"), "Financial Markets"
        )


class ResolveSpecializationTest(unittest.TestCase):
    def test_picks_the_candidate_whose_title_matches(self):
        html = og("Deep Learning") + '<a href="/learn/neural-networks-deep-learning">x</a>'

        def fetch(url):
            return html

        with TemporaryDirectory() as tmp:
            slug, page = resolve_specialization(
                {"title": "Deep Learning Specialization"},
                ["deep-learning", "deep-learning-with-python"],
                fetch=fetch,
                delay=0,
                cache_dir=Path(tmp),
            )

        self.assertEqual(slug, "deep-learning")
        self.assertEqual(page, html)

    def test_a_wrong_title_is_not_accepted(self):
        def fetch(url):
            return og("Something Else Entirely")

        with TemporaryDirectory() as tmp:
            slug, page = resolve_specialization(
                {"title": "Deep Learning Specialization"},
                ["deep-learning"],
                fetch=fetch,
                delay=0,
                cache_dir=Path(tmp),
            )

        self.assertIsNone(slug)
        self.assertIsNone(page)

    def test_a_dead_candidate_does_not_stop_the_next_one(self):
        def fetch(url):
            if url.endswith("/deep-learning"):
                raise RuntimeError("404")
            return og("Machine Learning")

        with TemporaryDirectory() as tmp:
            slug, _page = resolve_specialization(
                {"title": "Machine Learning Specialization"},
                ["deep-learning", "machine-learning"],
                fetch=fetch,
                delay=0,
                cache_dir=Path(tmp),
            )

        self.assertEqual(slug, "machine-learning")


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {
                "title": "Deep Learning Specialization",
                "issuer": "Coursera",
                "type": "specialization",
            }
        ]
        self.specialization_page = (
            og("Deep Learning")
            + '<a href="/learn/course-a?specialization=deep-learning" '
            + 'data-e2e="sdp-course-list-link">A</a>'
            + '<a href="/learn/course-a-fr?specialization=deep-learning" '
            + 'data-e2e="sdp-course-list-link">A (fr)</a>'
            + '<a href="/learn/course-b?specialization=deep-learning" '
            + 'data-e2e="sdp-course-list-link">B</a>'
        )

    def test_lists_constituent_courses_and_skips_what_is_already_known(self):
        def fetch(url):
            return self.specialization_page

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            slug_cache = tmp / "specializations.txt"
            slug_cache.write_text("deep-learning\n", encoding="utf-8")

            new, lines = plan(
                {},
                self.entries,
                existing=["learn/course-a"],
                fetch=fetch,
                delay=0,
                cache_dir=tmp / "pages",
                slug_cache=slug_cache,
            )

        self.assertEqual(list(new), ["learn/course-b"])
        self.assertIn("specialization:deep-learning", new["learn/course-b"])
        self.assertTrue(any("already listed" in line for line in lines))

    def test_instructors_contribute_the_courses_they_teach(self):
        scores = {
            "learn/course-a": {
                "instructors": [{"name": "Ada", "slug": "ada"}],
            }
        }
        profile = (
            og("Ada, Instructor")
            + '<a href="/learn/course-c"><div data-e2e="course-card">C</div></a>'
            + '<a href="/learn/course-c-es"><div data-e2e="course-card">C (es)</div></a>'
        )

        def fetch(url):
            return profile

        with TemporaryDirectory() as tmp:
            new, _lines = plan(
                scores,
                [],
                fetch=fetch,
                delay=0,
                cache_dir=Path(tmp),
                specializations=False,
                instructors=True,
            )

        self.assertEqual(list(new), ["learn/course-c"])
        self.assertEqual(new["learn/course-c"], ["instructor:ada"])

    def test_a_parent_page_that_dies_is_reported_not_raised(self):
        def fetch(url):
            raise RuntimeError("boom")

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            slug_cache = tmp / "specializations.txt"
            slug_cache.write_text("deep-learning\n", encoding="utf-8")
            new, lines = plan(
                {},
                self.entries,
                fetch=fetch,
                delay=0,
                cache_dir=tmp / "pages",
                slug_cache=slug_cache,
            )

        self.assertEqual(new, {})
        self.assertTrue(any(line.strip().startswith("miss") for line in lines))


class LoadSlugsTest(unittest.TestCase):
    def test_downloads_once_then_reads_the_cache(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return (
                "<url><loc>https://www.coursera.org/specializations/deep-learning</loc></url>"
                "<url><loc>https://www.coursera.org/learn/machine-learning</loc></url>"
            )

        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "specializations.txt"
            first = load_slugs(fetch=fetch, cache_path=cache)
            second = load_slugs(fetch=fetch, cache_path=cache)

        self.assertEqual(first, ["deep-learning"])
        self.assertEqual(second, ["deep-learning"])
        self.assertEqual(len(calls), 1)


class IndexedInstructorsTest(unittest.TestCase):
    def test_one_entry_per_person_even_across_courses(self):
        scores = {
            "learn/a": {"instructors": [{"name": "Ada", "slug": "ada"}]},
            "learn/b": {"instructors": [{"name": "Ada", "slug": "ada"}]},
            "learn/c": {"instructors": [{"name": "No slug", "slug": None}]},
        }

        people = indexed_instructors(scores)

        self.assertEqual(list(people), ["ada"])


if __name__ == "__main__":
    unittest.main()
