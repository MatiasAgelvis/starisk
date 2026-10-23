import unittest

from starisk.add import classify, merge, sources_from_text


class ClassifyTest(unittest.TestCase):
    def test_accepts_the_shapes_a_person_actually_pastes(self):
        for raw in (
            "learn/machine-learning",
            "/learn/machine-learning/",
            "https://www.coursera.org/learn/machine-learning",
            "https://www.coursera.org/learn/machine-learning/reviews",
            "machine-learning",
        ):
            self.assertEqual(classify(raw), "learn/machine-learning", raw)

    def test_accepts_specializations_but_not_random_paths(self):
        self.assertEqual(
            classify("https://www.coursera.org/specializations/deep-learning"),
            "specializations/deep-learning",
        )
        self.assertIsNone(classify("https://www.coursera.org/instructor/andrewng"))
        self.assertIsNone(classify("https://www.coursera.org/account/accomplishments/x"))

    def test_rejects_garbage(self):
        self.assertIsNone(classify(""))
        self.assertIsNone(classify("   "))
        self.assertIsNone(classify("not a slug at all"))


class SourcesFromTextTest(unittest.TestCase):
    def test_one_per_line_ignores_blanks_and_comments(self):
        text = "\n# my picks\nhttps://www.coursera.org/learn/a\n\n  learn/b  \n"
        self.assertEqual(
            sources_from_text(text),
            ["https://www.coursera.org/learn/a", "learn/b"],
        )


class MergeTest(unittest.TestCase):
    def test_dedupes_against_the_list_and_itself(self):
        added, duplicates, invalid, merged = merge(
            [
                "learn/new-one",
                "https://www.coursera.org/learn/old-one",
                "new-one",
                "https://www.coursera.org/instructor/x",
            ],
            ["learn/old-one"],
        )

        self.assertEqual(added, ["learn/new-one"])
        # The repeated slug is a duplicate of the one added earlier in this batch.
        self.assertEqual(duplicates, ["learn/old-one", "learn/new-one"])
        self.assertEqual(len(invalid), 1)
        self.assertEqual(merged, ["learn/old-one", "learn/new-one"])

    def test_does_not_mutate_the_existing_list(self):
        existing = ["learn/a"]
        merge(["learn/b"], existing)
        self.assertEqual(existing, ["learn/a"])


if __name__ == "__main__":
    unittest.main()
