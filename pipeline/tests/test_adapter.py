import math
import unittest
from pathlib import Path

from starisk.adapter import (
    extract_aggregate,
    extract_coursera_score,
    extract_details,
    extract_population,
    extract_reviews,
    extract_title,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"


class AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = FIXTURE.read_text(encoding="utf-8")

    def test_reads_the_aggregate_rating_from_json_ld(self):
        self.assertEqual(extract_coursera_score(self.html), 4.9)

    def test_reads_the_display_name_from_json_ld(self):
        self.assertEqual(extract_title(self.html), "Sample Course")

    def test_reads_course_details_from_json_ld(self):
        details = extract_details(self.html)
        self.assertEqual(details["title"], "Sample Course")
        self.assertEqual(details["provider"], "Test University")
        self.assertEqual(details["image"], "https://example.com/image.png")
        self.assertIn("sample course", details["description"].lower())

    def test_captures_review_text(self):
        first = extract_reviews(self.html)[0]
        self.assertIn("rushed", first["text"])

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


class AggregateTest(unittest.TestCase):
    def test_rating_and_population(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","aggregateRating":'
            '{"ratingValue":"4.8","ratingCount":"32,331","reviewCount":"7108"}}'
            "</script>"
        )
        aggregate = extract_aggregate(html)

        self.assertEqual(aggregate["rating"], 4.8)
        self.assertEqual(aggregate["ratings_total"], 32331)
        self.assertEqual(aggregate["reviews_total"], 7108)

    def test_missing_aggregate_is_nan(self):
        aggregate = extract_aggregate("<html></html>")

        self.assertIsNone(aggregate["rating"])
        self.assertIsNone(aggregate["reviews_total"])
        self.assertTrue(math.isnan(extract_coursera_score("<html></html>")))

    def test_review_count_without_rating_count(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","aggregateRating":'
            '{"ratingValue":"4.9","reviewCount":"6214"}}'
            "</script>"
        )
        aggregate = extract_aggregate(html)

        self.assertEqual(aggregate["reviews_total"], 6214)
        self.assertIsNone(aggregate["ratings_total"])


class ProviderFallbackTest(unittest.TestCase):
    def test_falls_back_to_provider_when_brand_is_absent(self):
        # IBM course pages use `provider`, not `brand`; missing this blanks the logo.
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"Django for Everybody",'
            '"provider":{"@type":"Organization","name":"IBM"}}'
            "</script>"
        )
        self.assertEqual(extract_details(html)["provider"], "IBM")

    def test_brand_wins_over_provider(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","name":"X",'
            '"brand":{"name":"Brand Co"},"provider":{"name":"Other"}}'
            "</script>"
        )
        self.assertEqual(extract_details(html)["provider"], "Brand Co")

    def test_level_and_enrollment_are_optional(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X","educationalLevel":"Intermediate",'
            '"totalHistoricalEnrollment":364000}'
            "</script>"
        )
        details = extract_details(html)

        self.assertEqual(details["level"], "Intermediate")
        self.assertEqual(details["enrollment"], 364000)

    def test_absent_metadata_is_none(self):
        html = '<script type="application/ld+json">{"@type":"Course","name":"X"}</script>'
        details = extract_details(html)

        self.assertIsNone(details["level"])
        self.assertIsNone(details["enrollment"])


class PopulationTest(unittest.TestCase):
    BLOB = (
        '"ratingCountsByStar":{"__typename":"X","fiveStarRatingCount":255087,'
        '"fourStarRatingCount":41384,"threeStarRatingCount":6492,'
        '"twoStarRatingCount":1495,"oneStarRatingCount":1641},'
        '"ratings":{"__typename":"Y","averageFiveStarRating":4.784398526785658}'
    )

    def test_counts_and_average(self):
        population = extract_population(self.BLOB)

        self.assertEqual(population["counts"], {1: 1641, 2: 1495, 3: 6492, 4: 41384, 5: 255087})
        self.assertEqual(population["total"], 306099)
        self.assertAlmostEqual(population["average"], 4.784398526785658)

    def test_key_order_does_not_matter(self):
        blob = (
            '"ratingCountsByStar":{"oneStarRatingCount":1135,"threeStarRatingCount":3232,'
            '"fiveStarRatingCount":66451,"twoStarRatingCount":1057,"fourStarRatingCount":16486}'
        )
        self.assertEqual(extract_population(blob)["total"], 88361)

    def test_absent(self):
        population = extract_population("<html></html>")

        self.assertIsNone(population["counts"])
        self.assertIsNone(population["average"])

    def test_average_fills_in_for_a_missing_jsonld_rating(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","aggregateRating":{"ratingCount":"215972"}}'
            "</script>" + self.BLOB
        )
        aggregate = extract_aggregate(html)

        self.assertAlmostEqual(aggregate["rating"], 4.784398526785658)
        # The population total wins: it is the sum of the counts we store, so the
        # sample statement and the distribution can never disagree.
        self.assertEqual(aggregate["ratings_total"], 306099)
        self.assertIsNotNone(aggregate["counts"])


if __name__ == "__main__":
    unittest.main()
