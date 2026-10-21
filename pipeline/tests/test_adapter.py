import unittest
from pathlib import Path

from stellaid.adapter import extract_coursera_score, extract_reviews

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"


class AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = FIXTURE.read_text(encoding="utf-8")

    def test_reads_the_aggregate_rating_from_json_ld(self):
        self.assertEqual(extract_coursera_score(self.html), 4.9)

    def test_extracts_every_review_card(self):
        self.assertEqual(len(extract_reviews(self.html)), 3)

    def test_parses_stars_likes_and_dates(self):
        reviews = extract_reviews(self.html)

        self.assertEqual(reviews[0]["stars"], 1.0)
        self.assertEqual(reviews[0]["likes"], 80)
        self.assertGreater(reviews[0]["age_days"], 19000)

        self.assertEqual(reviews[1]["stars"], 5.0)
        self.assertEqual(reviews[1]["likes"], 3)

        self.assertEqual(reviews[2]["stars"], 3.5)
        self.assertEqual(reviews[2]["likes"], 12)

    def test_every_review_is_well_formed(self):
        for review in extract_reviews(self.html):
            self.assertGreaterEqual(review["stars"], 0)
            self.assertLessEqual(review["stars"], 5)
            self.assertGreaterEqual(review["likes"], 0)
            self.assertEqual(review["age_days"], review["age_days"])  # not NaN

    def test_falls_back_to_json_ld_when_there_are_no_cards(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","aggregateRating":{"ratingValue":"4.4"},
         "review":[
           {"@type":"Review","reviewRating":{"ratingValue":5},"datePublished":"2022-11-14"},
           {"@type":"Review","reviewRating":{"ratingValue":2},"datePublished":"2021-01-02"}
         ]}
        </script>
        """
        reviews = extract_reviews(html)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0]["stars"], 5.0)
        self.assertEqual(reviews[0]["likes"], 0)
        self.assertEqual(reviews[1]["stars"], 2.0)
        self.assertGreater(reviews[0]["age_days"], 19000)


if __name__ == "__main__":
    unittest.main()
