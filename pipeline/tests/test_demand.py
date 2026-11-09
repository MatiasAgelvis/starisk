import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from starisk.demand import (
    Demand,
    TursoError,
    build_plan,
    build_snapshot,
    execute,
    export_requests,
    handle,
    http_base,
    is_placeholder,
    locate_env,
    main,
    parse_args,
    parse_env,
    probe_course,
    queue_type,
    read_requests,
    resolve,
)


def demand(id, key, requests=1, kind="slug", query=None):
    return Demand(id=id, key=key, kind=kind, query=query or key, requests=requests)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def turso_reply(rows):
    return {
        "results": [
            {"type": "ok", "response": {"type": "execute", "result": {"rows": rows}}},
            {"type": "ok", "response": {"type": "close"}},
        ]
    }


class EnvTest(unittest.TestCase):
    def test_reads_assignments_comments_and_export(self):
        values = parse_env(
            """
            # the production database
            TURSO_DATABASE_URL=libsql://db.turso.io
            export TURSO_AUTH_TOKEN="secret"
            EMPTY=
            NOT_A_PAIR
            """
        )

        self.assertEqual(values["TURSO_DATABASE_URL"], "libsql://db.turso.io")
        self.assertEqual(values["TURSO_AUTH_TOKEN"], "secret")
        self.assertEqual(values["EMPTY"], "")
        self.assertNotIn("NOT_A_PAIR", values)

    def test_explicit_flag_then_file_then_shell(self):
        env = {"TURSO_DATABASE_URL": "env-url", "TURSO_AUTH_TOKEN": "env-token"}
        file = {"TURSO_DATABASE_URL": "file-url", "TURSO_AUTH_TOKEN": "file-token"}

        self.assertEqual(resolve(env, file), ("file-url", "file-token"))
        self.assertEqual(resolve(env, file, "cli-url", "cli-token"), ("cli-url", "cli-token"))
        self.assertEqual(resolve(env, {}), ("env-url", "env-token"))
        self.assertEqual(resolve({}, {}), (None, None))


class LocateEnvTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pipeline").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_prefers_the_shell_directory(self):
        (self.root / "pipeline" / ".env.dev").write_text("A=1")
        (self.root / ".env.dev").write_text("A=2")

        found = locate_env(".env.dev", cwd=self.root / "pipeline", root=self.root)

        self.assertEqual(found, self.root / "pipeline" / ".env.dev")

    def test_falls_back_to_the_repository_root(self):
        (self.root / ".env.prod").write_text("A=1")

        found = locate_env(".env.prod", cwd=self.root / "pipeline", root=self.root)

        self.assertEqual(found, self.root / ".env.prod")

    def test_absolute_paths_are_taken_as_given(self):
        path = self.root / ".env.prod"
        path.write_text("A=1")

        self.assertEqual(locate_env(str(path), cwd=self.root / "pipeline", root=self.root), path)

    def test_missing_file_is_none(self):
        self.assertIsNone(locate_env(".env.nope", cwd=self.root / "pipeline", root=self.root))


class HttpTest(unittest.TestCase):
    def test_libsql_urls_become_https(self):
        self.assertEqual(http_base("libsql://db.turso.io/"), "https://db.turso.io")
        self.assertEqual(http_base("https://db.turso.io"), "https://db.turso.io")
        self.assertEqual(http_base("http://127.0.0.1:8080"), "http://127.0.0.1:8080")


class ReadRequestsTest(unittest.TestCase):
    def test_reads_the_queue_and_turns_integer_cells_back_into_ints(self):
        calls = []

        def fetch(request, timeout=0):
            calls.append(request)
            rows = [
                [
                    {"type": "integer", "value": "7"},
                    {"type": "text", "value": "learn/machine-learning"},
                    {"type": "text", "value": "slug"},
                    {"type": "text", "value": "learn/machine-learning"},
                    {"type": "integer", "value": "3"},
                    {"type": "text", "value": "2026-01-01T00:00:00Z"},
                    {"type": "text", "value": "2026-01-02T00:00:00Z"},
                ]
            ]
            return FakeResponse(turso_reply(rows))

        [found] = read_requests("libsql://db.turso.io", "tok", fetch=fetch)

        self.assertEqual(
            found,
            Demand(
                7,
                "learn/machine-learning",
                "slug",
                "learn/machine-learning",
                3,
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
            ),
        )
        self.assertEqual(calls[0].full_url, "https://db.turso.io/v2/pipeline")
        self.assertEqual(calls[0].headers.get("Authorization"), "Bearer tok")

        body = json.loads(calls[0].data)
        self.assertEqual(body["requests"][-1], {"type": "close"})
        self.assertEqual(body["requests"][0]["stmt"]["sql"].split()[1], "id,")

    def test_surfaces_a_failed_statement(self):
        def fetch(request, timeout=0):
            return FakeResponse(
                {
                    "results": [
                        {
                            "type": "error",
                            "error": {"message": "no such table: course_requests"},
                        }
                    ]
                }
            )

        with self.assertRaises(TursoError) as caught:
            execute("https://db.turso.io", "tok", [("SELECT 1", [])], fetch=fetch)

        self.assertIn("no such table", str(caught.exception))


class BuildPlanTest(unittest.TestCase):
    def test_sorts_by_key_prefix(self):
        plan = build_plan(
            [
                demand(1, "learn/a", 3),
                demand(2, "learn/b", 1),
                demand(3, "professional-certificates/p", 2),
                demand(4, "specializations/s", 1),
                demand(5, "name/some course", 1, kind="name", query="Some Course"),
                demand(6, "weird"),
                demand(7, "learn"),
                demand(8, "instructor/~118561318", 2),
            ]
        )

        self.assertEqual([item.key for item in plan.courses], ["learn/a", "learn/b"])
        self.assertEqual(
            [item.key for item in plan.programs],
            ["professional-certificates/p", "specializations/s"],
        )
        self.assertEqual([item.key for item in plan.unresolved], ["name/some course"])
        self.assertEqual([item.key for item in plan.ignored], ["weird", "learn"])
        self.assertEqual([item.key for item in plan.teachers], ["instructor/~118561318"])

    def test_min_requests_filters_quiet_rows(self):
        plan = build_plan([demand(1, "learn/a", 3), demand(2, "learn/b", 1)], min_requests=2)

        self.assertEqual([item.key for item in plan.courses], ["learn/a"])

    def test_limit_applies_to_courses_and_programs_together(self):
        plan = build_plan(
            [
                demand(1, "learn/a"),
                demand(2, "learn/b"),
                demand(3, "professional-certificates/p"),
            ],
            limit=1,
        )

        self.assertEqual([item.key for item in plan.courses], ["learn/a"])
        self.assertEqual(plan.programs, [])

    def test_duplicate_ids_count_once(self):
        plan = build_plan([demand(1, "learn/a"), demand(1, "learn/a")])

        self.assertEqual(len(plan.courses), 1)


class HandleTest(unittest.TestCase):
    def test_decides_add_existing_gone_program_and_manual(self):
        plan = build_plan(
            [
                demand(1, "learn/new", 2),
                demand(2, "learn/existing", 1),
                demand(3, "learn/dead", 1),
                demand(4, "professional-certificates/p", 3),
                demand(5, "name/thing", 1, kind="name", query="Thing"),
            ]
        )
        checked, fetched = [], []

        def check(key):
            checked.append(key)
            return "Some Title" if key != "learn/dead" else None

        def fetch_programs(keys, delay=0):
            fetched.extend(keys)

        outcome = handle(
            plan,
            ["learn/existing"],
            [],
            check=check,
            known_titles={"learn/existing": "Existing Title"},
            sleep=lambda _: None,
            fetch_programs=fetch_programs,
            build=lambda: {
                "professional-certificates/p": {
                    "title": "Program P",
                    "courses": ["learn/m1", "learn/m2"],
                }
            },
        )

        self.assertEqual(
            outcome.sources,
            ["learn/existing", "learn/new", "learn/m1", "learn/m2"],
        )
        self.assertEqual(outcome.seeds, ["professional-certificates/p"])
        self.assertEqual([item.key for item in outcome.added_courses], ["learn/new"])
        self.assertEqual([item.key for item in outcome.existing_courses], ["learn/existing"])
        self.assertEqual([item.key for item in outcome.gone], ["learn/dead"])
        self.assertEqual([item.key for item in outcome.added_programs], ["professional-certificates/p"])
        self.assertEqual(outcome.member_courses, ["learn/m1", "learn/m2"])
        self.assertEqual(
            outcome.handled,
            ["learn/new", "learn/existing", "professional-certificates/p"],
        )
        self.assertEqual(
            outcome.titles,
            {"learn/new": "Some Title", "professional-certificates/p": "Program P"},
        )
        self.assertEqual([item.key for item in outcome.unresolved], ["name/thing"])
        self.assertEqual(checked, ["learn/new", "learn/dead"])
        self.assertEqual(fetched, ["professional-certificates/p"])

    def test_an_existing_course_can_backfill_its_title(self):
        plan = build_plan([demand(1, "learn/existing")])

        outcome = handle(
            plan,
            ["learn/existing"],
            [],
            check=lambda key: "Existing Title",
            known_titles={},
            sleep=lambda _: None,
            build=lambda: {},
        )

        self.assertEqual([item.key for item in outcome.existing_courses], ["learn/existing"])
        self.assertEqual(outcome.titles, {"learn/existing": "Existing Title"})

    def test_a_teacher_request_adds_their_courses(self):
        plan = build_plan(
            [
                demand(1, "instructor/~118561318", 2),
                demand(2, "instructor/missing", 1),
            ]
        )
        asked = []

        def fetch_teachers(slugs, delay=0, offline=False):
            asked.extend(slugs)
            return {"~118561318": ["learn/a", "learn/b"]}

        outcome = handle(
            plan,
            [],
            [],
            check=lambda key: True,
            sleep=lambda _: None,
            fetch_teachers=fetch_teachers,
            build=lambda: {},
        )

        self.assertEqual(asked, ["~118561318", "missing"])
        self.assertEqual([item.key for item in outcome.added_teachers], ["instructor/~118561318"])
        self.assertEqual(outcome.teacher_courses["~118561318"], ["learn/a", "learn/b"])
        self.assertEqual(outcome.sources, ["learn/a", "learn/b"])
        self.assertEqual(outcome.handled, ["instructor/~118561318"])
        self.assertEqual([item.key for item in outcome.waiting], ["instructor/missing"])

    def test_offline_touches_no_network(self):
        plan = build_plan([demand(1, "learn/new")])

        def boom(*args, **kwargs):
            raise AssertionError("no network in offline mode")

        outcome = handle(
            plan,
            [],
            [],
            offline=True,
            check=boom,
            sleep=boom,
            fetch_programs=boom,
            build=lambda: {},
        )

        self.assertEqual(outcome.sources, ["learn/new"])

    def test_a_program_already_seeded_is_not_added_twice(self):
        plan = build_plan([demand(1, "professional-certificates/p")])

        outcome = handle(
            plan,
            [],
            ["professional-certificates/p"],
            offline=True,
            fetch_programs=lambda *args, **kwargs: None,
            build=lambda: {"professional-certificates/p": {"courses": ["learn/m1"]}},
        )

        self.assertEqual(outcome.added_programs, [])
        self.assertEqual([item.key for item in outcome.existing_programs], ["professional-certificates/p"])
        self.assertEqual(outcome.sources, ["learn/m1"])
        self.assertEqual(outcome.handled, ["professional-certificates/p"])

    def test_a_program_without_a_cached_page_stays_new(self):
        plan = build_plan([demand(1, "professional-certificates/p")])

        outcome = handle(
            plan,
            [],
            [],
            offline=True,
            fetch_programs=lambda *args, **kwargs: None,
            build=lambda: {},
        )

        self.assertEqual([item.key for item in outcome.waiting], ["professional-certificates/p"])
        self.assertNotIn("professional-certificates/p", outcome.handled)


class ParseArgsTest(unittest.TestCase):
    def test_dry_run_is_the_default_and_can_be_stated(self):
        self.assertFalse(parse_args([]).write)
        self.assertFalse(parse_args(["--dry-run"]).write)
        self.assertTrue(parse_args(["--write"]).write)

    def test_write_and_dry_run_are_mutually_exclusive(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--write", "--dry-run"])

    def test_the_work_budget_flags(self):
        options = parse_args(["--min-requests", "2", "--limit", "7", "--offline"])

        self.assertEqual(options.min_requests, 2)
        self.assertEqual(options.limit, 7)
        self.assertTrue(options.offline)


class PlaceholderTest(unittest.TestCase):
    def test_detects_vercels_sensitive_marker(self):
        self.assertTrue(is_placeholder("{SENSITIVE}"))
        self.assertTrue(is_placeholder(" {sensitive} "))
        self.assertFalse(is_placeholder("libsql://db.turso.io"))
        self.assertFalse(is_placeholder(None))

    def test_main_stops_before_the_network(self):
        with redirect_stderr(io.StringIO()) as stderr:
            code = main(["--url", "libsql://db.turso.io", "--token", "{SENSITIVE}"])

        self.assertEqual(code, 1)
        self.assertIn("{SENSITIVE}", stderr.getvalue())


class ProbeCourseTest(unittest.TestCase):
    def test_liveness_and_title_come_from_one_request(self):
        def fetch(url):
            self.assertTrue(url.endswith("/learn/machine-learning/reviews"))
            return (
                '<script type="application/ld+json">'
                '{"@type":"Course","name":"Machine Learning"}</script>'
            )

        self.assertEqual(probe_course("learn/machine-learning", fetch=fetch), "Machine Learning")

    def test_a_dead_link_is_none(self):
        def fetch(url):
            raise RuntimeError("404")

        self.assertIsNone(probe_course("learn/gone", fetch=fetch))

    def test_alive_without_a_title_is_an_empty_string(self):
        self.assertEqual(probe_course("learn/x", fetch=lambda url: "<html></html>"), "")


class QueueSnapshotTest(unittest.TestCase):
    def test_types_follow_the_key_prefix(self):
        self.assertEqual(queue_type("learn/x"), "course")
        self.assertEqual(queue_type("specializations/x"), "specialization")
        self.assertEqual(queue_type("professional-certificates/x"), "professional-certificate")
        self.assertEqual(queue_type("instructor/x"), "instructor")
        self.assertEqual(queue_type("name/x"), "other")

    def test_snapshot_keeps_only_the_ask_fields(self):
        demands = [
            Demand(
                1,
                "learn/x",
                "slug",
                "learn/x",
                2,
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
            )
        ]

        snapshot = build_snapshot(
            demands,
            "2026-01-03T00:00:00Z",
            handled=["learn/x"],
            titles={"learn/x": "A Title"},
        )

        self.assertEqual(snapshot["generatedAt"], "2026-01-03T00:00:00Z")
        self.assertEqual(
            snapshot["rows"],
            [
                {
                    "key": "learn/x",
                    "type": "course",
                    "query": "learn/x",
                    "requests": 2,
                    "first_seen": "2026-01-01T00:00:00Z",
                    "last_seen": "2026-01-02T00:00:00Z",
                    "title": "A Title",
                    "added_at": "2026-01-03T00:00:00Z",
                }
            ],
        )

    def test_unhandled_requests_are_not_published(self):
        demands = [Demand(1, "name/thing", "name", "Thing", 1)]

        snapshot = build_snapshot(demands, "2026-01-03T00:00:00Z")

        self.assertEqual(snapshot["rows"], [])

    def test_previous_rows_keep_their_added_at(self):
        previous = {
            "rows": [
                {
                    "key": "learn/x",
                    "type": "course",
                    "query": "learn/x",
                    "requests": 2,
                    "first_seen": "2026-01-01T00:00:00Z",
                    "last_seen": "2026-01-02T00:00:00Z",
                    "title": "Old Title",
                    "added_at": "2026-01-02T12:00:00Z",
                }
            ]
        }
        demands = [Demand(1, "learn/x", "slug", "learn/x", 4)]

        snapshot = build_snapshot(demands, "2026-01-03T00:00:00Z", previous=previous)

        self.assertEqual(snapshot["rows"][0]["added_at"], "2026-01-02T12:00:00Z")
        self.assertEqual(snapshot["rows"][0]["requests"], 4)
        self.assertEqual(snapshot["rows"][0]["title"], "Old Title")

    def test_export_writes_the_local_ask_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requests.json"
            snapshot = export_requests(
                [Demand(1, "learn/x", "slug", "learn/x", 1)],
                handled=["learn/x"],
                titles={"learn/x": "A Title"},
                path=path,
                generated_at="2026-01-03T00:00:00Z",
            )

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), snapshot)
            self.assertEqual(snapshot["rows"][0]["title"], "A Title")


if __name__ == "__main__":
    unittest.main()
