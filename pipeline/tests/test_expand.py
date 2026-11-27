import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from starisk.expand import (
    indexed_instructors,
    parse_args,
    plan,
    publisher_candidates,
    read_publishers,
)


def og(title: str) -> str:
    return f'<meta data-rh="true" property="og:title" content="{title}"/>'


class PublisherCandidateTest(unittest.TestCase):
    def test_flags_accounts_that_look_like_their_provider(self):
        scores = {
            "learn/a": {
                "provider": "SkillUp",
                "instructors": [{"slug": "skillup", "name": "SkillUp"}],
            },
            "learn/b": {
                "provider": "IBM",
                "instructors": [{"slug": "ibm-skills-network", "name": "IBM Skills Network Team"}],
            },
            "learn/c": {
                "provider": "Coursera",
                "instructors": [{"slug": "jeff", "name": "Jeff Maggioncalda, Coursera CEO"}],
            },
        }

        found = publisher_candidates(scores, set())

        self.assertEqual([slug for slug, _ in found], ["ibm-skills-network", "skillup"])

    def test_the_verified_list_is_not_reported(self):
        scores = {
            "learn/a": {
                "provider": "SkillUp",
                "instructors": [{"slug": "skillup", "name": "SkillUp"}],
            }
        }

        self.assertEqual(publisher_candidates(scores, {"skillup"}), [])

    def test_reads_the_verified_list_and_survives_a_broken_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "publishers.json"
            path.write_text('{"skillup": "profile is the partner name"}', encoding="utf-8")
            self.assertEqual(read_publishers(path), {"skillup"})

            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            self.assertEqual(read_publishers(broken), set())
            self.assertEqual(read_publishers(Path(tmp) / "missing.json"), set())


class ParseArgsTest(unittest.TestCase):
    def test_defaults_to_both_levers(self):
        options = parse_args([])

        self.assertFalse(options.instructors)
        self.assertFalse(options.programs)
        self.assertFalse(options.write)

    def test_flags(self):
        options = parse_args(["--instructors", "--limit", "5", "--write"])

        self.assertTrue(options.instructors)
        self.assertEqual(options.limit, 5)
        self.assertTrue(options.write)

    def test_the_program_lever_has_its_own_flag(self):
        options = parse_args(["--programs"])

        self.assertTrue(options.programs)
        self.assertFalse(options.instructors)


class PlanTest(unittest.TestCase):
    def _scores(self):
        return {"learn/course-a": {"instructors": [{"name": "Ada", "slug": "ada"}]}}

    def test_instructors_contribute_the_courses_they_teach(self):
        profile = (
            og("Ada, Instructor")
            + '<a href="/learn/course-c"><div data-e2e="course-card">C</div></a>'
            + '<a href="/learn/course-c-es"><div data-e2e="course-card">C (es)</div></a>'
        )

        with TemporaryDirectory() as tmp:
            new, _lines = plan(
                self._scores(),
                fetch=lambda url: profile,
                delay=0,
                cache_dir=Path(tmp),
                instructors=True,
            )

        self.assertEqual(list(new), ["learn/course-c"])
        self.assertEqual(new["learn/course-c"], ["instructor:ada"])

    def test_an_already_listed_course_is_not_reported_as_new(self):
        profile = og("Ada") + '<a href="/learn/course-c"><div data-e2e="course-card">C</div></a>'

        with TemporaryDirectory() as tmp:
            new, lines = plan(
                self._scores(),
                existing=["learn/course-c"],
                fetch=lambda url: profile,
                delay=0,
                cache_dir=Path(tmp),
                instructors=True,
            )

        self.assertEqual(new, {})
        self.assertTrue(any("already listed 1" in line for line in lines))

    def test_a_retired_course_is_not_added_back(self):
        profile = og("Ada") + '<a href="/learn/course-c"><div data-e2e="course-card">C</div></a>'

        with TemporaryDirectory() as tmp:
            new, lines = plan(
                self._scores(),
                fetch=lambda url: profile,
                delay=0,
                cache_dir=Path(tmp),
                instructors=True,
                retired={"learn/course-c": {"at": "2026-11-24"}},
            )

        self.assertEqual(new, {})
        self.assertTrue(any("retired 1" in line for line in lines))

    def test_streams_progress_as_each_parent_page_finishes(self):
        profile = og("Ada") + '<a href="/learn/course-c"><div data-e2e="course-card">C</div></a>'
        seen = []

        with TemporaryDirectory() as tmp:
            plan(
                self._scores(),
                fetch=lambda url: profile,
                delay=0,
                cache_dir=Path(tmp),
                instructors=True,
                log=seen.append,
            )

        self.assertTrue(any(line.startswith("[1/1") for line in seen))
        self.assertTrue(any("ok" in line and "Ada" in line for line in seen))

    def test_a_parent_page_that_dies_is_reported_not_raised(self):
        def fetch(url):
            raise RuntimeError("boom")

        with TemporaryDirectory() as tmp:
            new, lines = plan(
                self._scores(),
                fetch=fetch,
                delay=0,
                cache_dir=Path(tmp),
                instructors=True,
            )

        self.assertEqual(new, {})
        self.assertTrue(any(line.strip().startswith("miss") for line in lines))

    def test_program_members_join_the_queue(self):
        index = {
            "specializations/a": {
                "title": "A",
                "courses": ["learn/already-there", "learn/from-program", "learn/retired"],
            }
        }

        new, lines = plan(
            {},
            existing=["learn/already-there"],
            fetch=lambda url: "",
            delay=0,
            programs=True,
            program_index=index,
            retired={"learn/retired"},
        )

        self.assertEqual(list(new), ["learn/from-program"])
        self.assertEqual(new["learn/from-program"], ["program:specializations/a"])
        self.assertTrue(any("programs: 1 programs" in line for line in lines))


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
