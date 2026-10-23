import unittest

from starisk.calibration import correlate, disagreements, report, score_key


def course(title, slug, label=None):
    return {"title": title, "slug": slug, "label": label}


class ScoreKeyTest(unittest.TestCase):
    def test_bare_slug_gets_a_type(self):
        self.assertEqual(score_key({"slug": "machine-learning"}), "learn/machine-learning")

    def test_typed_slug_is_kept(self):
        self.assertEqual(score_key({"slug": "learn/x"}), "learn/x")

    def test_missing_slug(self):
        self.assertIsNone(score_key({"slug": ""}))
        self.assertIsNone(score_key({}))


class CorrelateTest(unittest.TestCase):
    def scores(self, **values):
        return {f"learn/{slug}": {"starisk": score} for slug, score in values.items()}

    def test_perfect_agreement(self):
        courses = [course("A", "a", 5), course("B", "b", 3), course("C", "c", 1)]
        rho, pairs = correlate(courses, self.scores(a=4.5, b=3.0, c=1.0))

        self.assertEqual(len(pairs), 3)
        self.assertAlmostEqual(rho, 1.0)

    def test_inverted_agreement(self):
        courses = [course("A", "a", 5), course("B", "b", 3), course("C", "c", 1)]
        rho, _ = correlate(courses, self.scores(a=1.0, b=3.0, c=4.5))

        self.assertAlmostEqual(rho, -1.0)

    def test_unlabelled_and_unscored_are_skipped(self):
        courses = [course("A", "a", 5), course("B", "b"), course("C", "c", 2)]
        rho, pairs = correlate(courses, self.scores(a=4.0))

        self.assertEqual(len(pairs), 1)
        self.assertIsNone(rho)  # one pair cannot correlate

    def test_nothing_to_compare(self):
        rho, pairs = correlate([course("A", "a")], self.scores(a=4.0))
        self.assertIsNone(rho)
        self.assertEqual(pairs, [])


class ReportTest(unittest.TestCase):
    def test_counts_and_blocks(self):
        courses = [
            course("A", "a", 5),
            course("B", "b"),
            course("C", "c", 2),  # labelled but absent from scores
        ]
        result = report(courses, {"learn/a": {"starisk": 4.0}})

        self.assertEqual(result["mapped"], 3)
        self.assertEqual(result["labelled"], 2)
        self.assertEqual(result["comparable"], 1)
        self.assertEqual(result["unscored"], ["C"])


class DisagreementTest(unittest.TestCase):
    def test_biggest_gap_first(self):
        pairs = [
            (course("Agrees", "a", 5), 4.9),
            (course("Way off", "b", 5), 1.0),
            (course("Slightly off", "c", 4), 3.0),
            (course("Inverted", "d", 1), 4.0),
        ]
        rows = disagreements(pairs)

        self.assertEqual(rows[0]["title"], "Way off")
        self.assertLess(abs(rows[-1]["delta"]), abs(rows[0]["delta"]))

    def test_needs_two_pairs(self):
        self.assertEqual(disagreements([(course("A", "a", 5), 4.0)]), [])


if __name__ == "__main__":
    unittest.main()
