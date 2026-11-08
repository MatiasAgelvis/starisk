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
    execute,
    handle,
    http_base,
    is_placeholder,
    locate_env,
    main,
    parse_args,
    parse_env,
    read_requests,
    resolve,
    status_update,
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
                ]
            ]
            return FakeResponse(turso_reply(rows))

        [found] = read_requests("libsql://db.turso.io", "tok", fetch=fetch)

        self.assertEqual(found, Demand(7, "learn/machine-learning", "slug", "learn/machine-learning", 3))
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
            ]
        )

        self.assertEqual([item.key for item in plan.courses], ["learn/a", "learn/b"])
        self.assertEqual(
            [item.key for item in plan.programs],
            ["professional-certificates/p", "specializations/s"],
        )
        self.assertEqual([item.key for item in plan.unresolved], ["name/some course"])
        self.assertEqual([item.key for item in plan.ignored], ["weird", "learn"])

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
            return key != "learn/dead"

        def fetch_programs(keys, delay=0):
            fetched.extend(keys)

        outcome = handle(
            plan,
            ["learn/existing"],
            [],
            check=check,
            sleep=lambda _: None,
            fetch_programs=fetch_programs,
            build=lambda: {"professional-certificates/p": {"courses": ["learn/m1", "learn/m2"]}},
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
        self.assertEqual(outcome.handled, [1, 2, 4])
        self.assertEqual([item.key for item in outcome.unresolved], ["name/thing"])
        self.assertEqual(checked, ["learn/new", "learn/dead"])
        self.assertEqual(fetched, ["professional-certificates/p"])

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
        self.assertEqual(outcome.handled, [1])

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
        self.assertNotIn(1, outcome.handled)


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


class StatusUpdateTest(unittest.TestCase):
    def test_one_placeholder_per_row(self):
        sql, args = status_update([3, 8])

        self.assertEqual(sql, "UPDATE course_requests SET status = 'planned' WHERE id IN (?, ?)")
        self.assertEqual(args, [3, 8])


if __name__ == "__main__":
    unittest.main()
