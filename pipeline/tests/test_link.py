import unittest

from starisk.link import candidates, clean_title, confirm, page_title, resolve, score, slug_tokens, tokens

SLUGS = [
    "convolutional-neural-networks-tensorflow",
    "convolutional-neural-networks",
    "sequence-models",
    "nlp-sequence-models",
    "programming-languages-part-a",
    "programming-languages-part-b",
    "machine-learning",
    "financial-markets",
    "getting-started-with-tensorflow-2",
]


class TokensTest(unittest.TestCase):
    def test_drops_stopwords_and_punctuation(self):
        self.assertEqual(tokens("Convolutional Neural Networks in TensorFlow"), {"convolutional", "neural", "networks", "tensorflow"})
        self.assertEqual(tokens("Machine-Learning, Part 2!"), {"machine", "learning", "part", "2"})
        self.assertEqual(tokens(""), set())

    def test_slug_tokens(self):
        self.assertEqual(slug_tokens("programming-languages-part-b"), {"programming", "languages", "part", "b"})


class ScoreTest(unittest.TestCase):
    def test_exact_match_beats_partial(self):
        wanted = tokens("Convolutional Neural Networks")
        exact = score(wanted, slug_tokens("convolutional-neural-networks"))
        extra = score(wanted, slug_tokens("convolutional-neural-networks-tensorflow"))
        unrelated = score(wanted, slug_tokens("financial-markets"))
        self.assertEqual(exact, 1.0)
        self.assertGreater(exact, extra)
        self.assertGreater(extra, unrelated)


class CandidatesTest(unittest.TestCase):
    def test_returns_best_first_and_ignores_junk(self):
        ranked = candidates("Convolutional Neural Networks in TensorFlow", SLUGS)
        self.assertEqual(ranked[0][0], "convolutional-neural-networks-tensorflow")
        self.assertTrue(all(value >= 0.35 for _, value in ranked))

    def test_part_letters_disambiguate(self):
        ranked = candidates("Programming Languages, Part B", SLUGS)
        self.assertEqual(ranked[0][0], "programming-languages-part-b")

    def test_nothing_similar(self):
        self.assertEqual(candidates("Introduction to Enumerative Combinatorics", SLUGS), [])


class PageTitleTest(unittest.TestCase):
    def test_strips_the_reviews_wrapper(self):
        page = '<meta data-rh="true" property="og:title" content="Learner Reviews &amp; Feedback for Financial Markets Course | Coursera">'
        self.assertEqual(page_title(page), "Financial Markets")

    def test_attribute_order_does_not_matter(self):
        page = '<meta content="Learner Reviews &amp; Feedback for Sequence Models Course | Coursera" property="og:title">'
        self.assertEqual(page_title(page), "Sequence Models")

    def test_specialization_wrapper(self):
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Deep Learning Specialization | Coursera">'
        self.assertEqual(page_title(page), "Deep Learning")

    def test_missing(self):
        self.assertEqual(page_title("<html></html>"), "")


class CleanTitleTest(unittest.TestCase):
    def test_strips_credential_decorations(self):
        self.assertEqual(clean_title("Financial Markets (with Honors)"), "Financial Markets")
        self.assertEqual(clean_title("Foundations (With Honours)"), "Foundations")
        self.assertEqual(clean_title("Capstone: Autonomous Runway Detection for IoT"), "Autonomous Runway Detection for IoT")
        self.assertEqual(clean_title("A Complete RL System (Capstone)"), "A Complete RL System (Capstone)")


class ConfirmTest(unittest.TestCase):
    def test_matching_title(self):
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Financial Markets Course">'
        self.assertTrue(confirm("financial-markets", "Financial Markets (with Honors)", fetch=lambda _: page))

    def test_subset_title_is_not_enough(self):
        # 'Ordered Data Structures' must not resolve to a generic 'Data Structures'.
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Data Structures Course">'
        self.assertFalse(confirm("data-structures", "Ordered Data Structures", fetch=lambda _: page))

    def test_wrong_course(self):
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Financial Markets Course">'
        self.assertFalse(confirm("sequence-models", "Sequence Models", fetch=lambda _: page))

    def test_404_is_not_a_match(self):
        def failing(_):
            raise RuntimeError("404")

        self.assertFalse(confirm("nope", "Sequence Models", fetch=failing))

    def test_honors_suffix_still_matches(self):
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Foundations for Big Data Analysis with SQL Course">'
        self.assertTrue(
            confirm(
                "foundations-big-data-analysis-sql",
                "Foundations for Big Data Analysis with SQL (with Honors)",
                fetch=lambda _: page,
            )
        )

    def test_reused_slug_is_rejected(self):
        # /learn/machine-learning now serves a rewritten course; the 2019
        # certificate's course is gone, and scoring the new one would be a lie.
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Supervised Machine Learning: Regression and Classification Course">'
        self.assertFalse(confirm("machine-learning", "Machine Learning", fetch=lambda _: page))

    def test_uses_the_reviews_url(self):
        seen = []

        def capture(url):
            seen.append(url)
            return '<meta property="og:title" content="Learner Reviews &amp; Feedback for Sequence Models Course">'

        confirm("sequence-models", "Sequence Models", fetch=capture)
        self.assertEqual(seen, ["https://www.coursera.org/learn/sequence-models/reviews"])


class ResolveTest(unittest.TestCase):
    def test_two_credentials_for_one_course_are_ambiguous(self):
        entries = [
            {"title": "Financial Markets", "issuer": "Coursera", "type": "course"},
            {"title": "Financial Markets (with Honors)", "issuer": "Coursera", "type": "course"},
        ]
        page = '<meta property="og:title" content="Learner Reviews &amp; Feedback for Financial Markets Course">'
        results = resolve(entries, ["financial-markets"], fetch=lambda _: page)

        self.assertEqual([r["slug"] for r in results], [None, None])
        self.assertEqual(results[0]["ambiguous_with"], ["Financial Markets (with Honors)"])

    def test_skips_non_coursera_and_specializations(self):
        entries = [
            {"title": "Some Udemy Thing", "issuer": "Udemy", "type": "course"},
            {"title": "Deep Learning Specialization", "issuer": "Coursera", "type": "specialization"},
        ]
        self.assertEqual(resolve(entries, [], fetch=lambda _: ""), [])


if __name__ == "__main__":
    unittest.main()
