import math
import unittest
from pathlib import Path

from starisk.adapter import (
    extract_aggregate,
    extract_coursera_score,
    extract_details,
    extract_landing,
    extract_instructor_courses,
    extract_population,
    extract_reviews,
    extract_specialization_courses,
    extract_title,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "review_cards.html"


def names(html: str) -> list[str]:
    return [record["name"] for record in extract_landing(html)["instructors"]]


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


class LandingTest(unittest.TestCase):
    def test_single_instructor_from_jsonld(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"instructor":{"@type":"Person","name":"Andrew Ng"}}'
            "</script>"
        )
        self.assertEqual(names(html), ["Andrew Ng"])

    def test_multiple_instructors(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"instructor":[{"name":"Ada"},{"name":"Grace"}]}'
            "</script>"
        )
        self.assertEqual(names(html), ["Ada", "Grace"])

    def test_instructors_from_the_data_blob_when_jsonld_is_silent(self):
        html = (
            '"instructors":[{"__ref":"DescriptionPage_Instructor:1244"}]'
            '"DescriptionPage_Instructor:1244":{"__typename":"X","name":"Andrew Ng"}'
        )
        self.assertEqual(names(html), ["Andrew Ng"])

    def test_blob_uses_full_name(self):
        # The real page uses `fullName`, plus fields that come before it.
        html = (
            '"instructors":[{"__ref":"DescriptionPage_Instructor:1244"}]'
            '"DescriptionPage_Instructor:1244":{"__typename":"X","id":"1244",'
            '"coursesTaught":53,"department":"Founder","fullName":"Andrew Ng",'
            '"isTopInstructor":true}'
        )
        self.assertEqual(names(html), ["Andrew Ng"])

    def test_the_page_data_gives_the_whole_teaching_team(self):
        # The hero links only the first instructor; the blob has all of them,
        # with an id, a profile picture and the job title.
        html = (
            '"instructors":[{"__ref":"DescriptionPage_Instructor:1"},'
            '{"__ref":"DescriptionPage_Instructor:2"}]'
            '"DescriptionPage_Instructor:1":{"id":"1","fullName":"Andrew Ng",'
            '"shortName":"andrewng","title":"Instructor",'
            '"department":"DeepLearning.AI","learnersReached":10040895,'
            '"coursesTaught":53,"photo":"https://example.com/ng.jpg"},'
            '"DescriptionPage_Instructor:2":{"id":"2","fullName":"Aarti Bagul",'
            '"shortName":"","title":"Curriculum Engineer","department":"",'
            '"learnersReached":1312880,"coursesTaught":6,"photo":null}'
        )
        team = extract_landing(html)["instructors"]

        self.assertEqual([person["name"] for person in team], ["Andrew Ng", "Aarti Bagul"])
        self.assertEqual(team[0]["slug"], "andrewng")
        self.assertEqual(team[0]["page"], "andrewng")
        self.assertEqual(team[0]["courses_taught"], 53)
        self.assertEqual(team[0]["role"], "Instructor")
        # No vanity slug: the numeric ref is still a real profile, but a readable
        # URL is better than `/instructors/~2`.
        self.assertEqual(team[1]["slug"], "~2")
        self.assertEqual(team[1]["url"], "https://www.coursera.org/instructor/~2")
        self.assertEqual(team[1]["page"], "aarti-bagul")

    def test_profile_link_gives_the_instructor_an_identity(self):
        html = (
            '<a href="/instructor/andrewng" class="x"><span class="y">Andrew Ng</span></a>'
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X","instructor":{"name":"Andrew Ng"}}'
            "</script>"
        )
        self.assertEqual(
            extract_landing(html)["instructors"],
            [
                {
                    "name": "Andrew Ng",
                    "slug": "andrewng",
                    "url": "https://www.coursera.org/instructor/andrewng",
                    "page": "andrewng",
                    "id": None,
                    "role": None,
                    "department": None,
                    "learners": None,
                    "courses_taught": None,
                    "photo": None,
                }
            ],
        )

    def test_anonymous_profile_slug_falls_back_to_the_name(self):
        html = '<a href="/instructor/~219741545"><span>Kara Pritchard</span></a>'
        self.assertEqual(extract_landing(html)["instructors"][0]["page"], "kara-pritchard")

    def test_instructor_names_are_normalised(self):
        html = '<a href="/instructor/~873260"><span>Dan  Grossman</span></a>'
        record = extract_landing(html)["instructors"][0]
        self.assertEqual(record["name"], "Dan Grossman")
        self.assertEqual(record["page"], "dan-grossman")

    def test_a_teacher_without_a_profile_is_kept(self):
        html = (
            '<a href="/instructor/andrewng"><span>Andrew Ng</span></a>'
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"instructor":[{"name":"Andrew Ng"},{"name":"Ada"}]}'
            "</script>"
        )
        self.assertEqual(names(html), ["Andrew Ng", "Ada"])
        self.assertIsNone(extract_landing(html)["instructors"][1]["slug"])

    def test_categories_from_domains(self):
        html = (
            '"domains":['
            '{"domainName":"Data Science","subdomainId":"ml","subdomainName":"Machine Learning"},'
            '{"domainName":"Computer Science","subdomainId":"algorithms","subdomainName":"Algorithms"}]'
        )
        self.assertEqual(extract_landing(html)["categories"], ["Data Science", "Computer Science"])

    def test_nothing(self):
        self.assertEqual(
            extract_landing("<html></html>"), {"instructors": [], "categories": []}
        )


class ProviderTest(unittest.TestCase):
    def test_a_provider_list_is_not_a_provider(self):
        # Some pages put the *instructors* under `provider`; that is not a brand.
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"provider":[{"@type":"Person","name":"Andrew Ng"},'
            '{"@type":"Person","name":"Isa Fulford"}]}'
            "</script>"
        )
        self.assertIsNone(extract_details(html)["provider"])

    def test_a_single_person_is_not_a_provider(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"provider":{"@type":"Person","name":"Laurence Moroney"}}'
            "</script>"
        )
        self.assertIsNone(extract_details(html)["provider"])

    def test_brand_dict_and_string_both_work(self):
        as_dict = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"brand":{"@type":"Organization","name":"DeepLearning.AI"}}'
            "</script>"
        )
        as_string = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X","provider":"DeepLearning.AI"}'
            "</script>"
        )
        as_org = (
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"X",'
            '"provider":{"@type":"Organization","name":"DeepLearning.AI"}}'
            "</script>"
        )
        self.assertEqual(extract_details(as_dict)["provider"], "DeepLearning.AI")
        self.assertEqual(extract_details(as_string)["provider"], "DeepLearning.AI")
        self.assertEqual(extract_details(as_org)["provider"], "DeepLearning.AI")


class GenericTitleTest(unittest.TestCase):
    def test_the_site_boilerplate_is_not_a_course_title(self):
        html = '<meta property="og:title" content="Coursera | Online Courses From Top Universities. Join for Free"/>'
        self.assertIsNone(extract_title(html))
        self.assertIsNone(extract_details(html)["title"])

    def test_it_falls_through_to_a_real_title(self):
        html = (
            '<meta property="og:title" content="Coursera Plus">'
            '<script type="application/ld+json">'
            '{"@type":"Course","name":"Medical Billing"}'
            "</script>"
        )
        self.assertEqual(extract_title(html), "Medical Billing")

    def test_a_real_title_survives(self):
        html = '<meta property="og:title" content="Real Course | Coursera"/>'
        self.assertEqual(extract_title(html), "Real Course | Coursera")


class CourseListTest(unittest.TestCase):
    def test_specialization_lists_its_courses(self):
        html = (
            '<a href="/learn/neural-networks-deep-learning?specialization=deep-learning" '
            'aria-label="Course 1: Neural Networks" data-e2e="sdp-course-list-link">1</a>'
            '<a href="/learn/deep-neural-network?specialization=deep-learning" '
            'data-e2e="sdp-course-list-link">2</a>'
        )
        self.assertEqual(
            extract_specialization_courses(html),
            ["neural-networks-deep-learning", "deep-neural-network"],
        )

    def test_instructor_profile_lists_their_courses(self):
        # The hook sits on a div inside the anchor, not on the anchor itself.
        html = (
            '<a href="/learn/ai-for-everyone" class="x">'
            '<div data-e2e="course-card">card</div></a>'
            '<a href="/learn/ai-for-everyone-fr" class="x">'
            '<div data-e2e="course-card">card</div></a>'
        )
        self.assertEqual(extract_instructor_courses(html), ["ai-for-everyone"])

    def test_language_variants_and_duplicates_are_dropped(self):
        html = (
            '<a href="/learn/course-a-fr" data-e2e="sdp-course-list-link">x</a>'
            '<a href="/learn/course-a" data-e2e="sdp-course-list-link">x</a>'
            '<a href="/learn/course-a" data-e2e="sdp-course-list-link">x</a>'
            '<a href="/specializations/not-a-course" data-e2e="sdp-course-list-link">x</a>'
        )
        self.assertEqual(extract_specialization_courses(html), ["course-a"])

    def test_nothing(self):
        self.assertEqual(extract_specialization_courses("<html></html>"), [])
        self.assertEqual(extract_instructor_courses("<html></html>"), [])


class ScriptTextTest(unittest.TestCase):
    def test_serialised_json_is_not_a_review(self):
        html = (
            'data-e2e="review-table-card"'
            '<div aria-label="Rated 1.0 out of 5 stars"></div>'
            '<div aria-label="This was helpful (5)"></div>'
            "Nov 14, 2022"
            '<script>var x = "' + "a" * 80 + '";</script>'
            "<p>The real review text, which is quite long and should win over the JSON.</p>"
        )
        reviews = extract_reviews(html)

        self.assertTrue(reviews)
        self.assertIn("real review", reviews[0]["text"])
        self.assertNotIn("aaaa", reviews[0]["text"])

    def test_footer_text_after_the_last_card_is_not_a_review(self):
        card = (
            'data-e2e="review-table-card"'
            '<div aria-label="Rated 1.0 out of 5 stars"></div>'
            '<div aria-label="This was helpful (5)"></div>'
            "Nov 14, 2022"
            '<div data-testid="cml-viewer"><p>The review body, long enough to be picked up here.</p></div>'
        )
        footer = "<footer>" + ("A far longer sidebar heading about unrelated certifications. " * 40) + "</footer>"
        reviews = extract_reviews(card + footer)

        self.assertIn("review body", reviews[0]["text"])
        self.assertNotIn("sidebar", reviews[0]["text"])


if __name__ == "__main__":
    unittest.main()
