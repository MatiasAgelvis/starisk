import unittest

from starisk.engine import (
    DEFAULTS,
    SIMPLE,
    course_score,
    peer_score,
    peer_spread,
    review_spread,
    review_weight,
)


class EngineTest(unittest.TestCase):
    def test_a_single_review_scores_as_its_own_star_value(self):
        self.assertAlmostEqual(
            peer_score([{"stars": 3, "likes": 0, "age_days": 18000}]), 3.0
        )

    def test_equal_weight_reviews_score_as_the_plain_mean(self):
        reviews = [
            {"stars": 5, "likes": 0, "age_days": 18000},
            {"stars": 1, "likes": 0, "age_days": 18000},
        ]
        self.assertAlmostEqual(peer_score(reviews), 3.0)

    def test_likes_dominate(self):
        reviews = [
            {"stars": 5, "likes": 0, "age_days": 18000},
            {"stars": 1, "likes": 100, "age_days": 18000},
        ]
        self.assertLess(peer_score(reviews), 2.0)

    def test_final_score_blends_peers_with_coursera(self):
        course = {
            "reviews": [{"stars": 3, "likes": 0, "age_days": 18000}],
            "coursera": 5.0,
        }
        # 0.8 * 3 + 0.2 * 5 = 3.4
        self.assertAlmostEqual(course_score(course), 3.4)

    def test_no_reviews_is_unverifiable(self):
        self.assertEqual(course_score({"reviews": [], "coursera": 4.5}), -1.0)

    def test_nan_coursera_falls_back_to_the_peer_score(self):
        course = {
            "reviews": [{"stars": 2, "likes": 0, "age_days": 18000}],
            "coursera": float("nan"),
        }
        self.assertAlmostEqual(course_score(course), 2.0)

    def test_custom_options_change_the_weighting(self):
        reviews = [
            {"stars": 5, "likes": 0, "age_days": 18000},
            {"stars": 1, "likes": 100, "age_days": 18000},
        ]
        peer_power_one = {**DEFAULTS, "peer_power": 1}
        self.assertGreater(
            peer_score(reviews, peer_power_one), peer_score(reviews, DEFAULTS)
        )

    def test_simple_model_weights_a_review_by_one_plus_likes(self):
        self.assertAlmostEqual(
            review_weight({"stars": 3, "likes": 4, "age_days": 18000}, SIMPLE), 5.0
        )
        reviews = [
            {"stars": 5, "likes": 0, "age_days": 18000},  # weight 1
            {"stars": 1, "likes": 4, "age_days": 18000},  # weight 5
        ]
        self.assertAlmostEqual(peer_score(reviews, SIMPLE), 10 / 6)

    def test_known_flaw_the_time_term_barely_moves(self):
        old = review_weight({"stars": 4, "likes": 10, "age_days": 17800}, DEFAULTS)
        recent = review_weight({"stars": 4, "likes": 10, "age_days": 19100}, DEFAULTS)
        ratio = recent / old
        self.assertGreater(ratio, 1.0)
        self.assertLess(ratio, 1.05)


class SpreadTest(unittest.TestCase):
    @staticmethod
    def review(stars, likes=0):
        return {"stars": stars, "likes": likes, "age_days": 1}

    def test_zero_when_everyone_agrees(self):
        reviews = [self.review(4.0), self.review(4.0, 10), self.review(4.0)]
        self.assertEqual(review_spread(reviews), 0.0)
        self.assertEqual(peer_spread(reviews, SIMPLE), 0.0)

    def test_split_reviews_are_wide(self):
        reviews = [self.review(1.0), self.review(5.0)]
        self.assertAlmostEqual(review_spread(reviews), 2.0)
        self.assertAlmostEqual(peer_spread(reviews, SIMPLE), 2.0)

    def test_review_spread_ignores_votes(self):
        quiet = [self.review(1.0), self.review(5.0), self.review(3.0)]
        loud = [self.review(1.0, 100), self.review(5.0), self.review(3.0)]
        self.assertAlmostEqual(review_spread(loud), review_spread(quiet))

    def test_weighted_spread_collapses_when_one_review_dominates(self):
        # The trap that made us split the metric: a 100-like 1-star review drags
        # the weighted mean to itself, so the *weighted* spread shrinks and a
        # contested course would look unanimous. Do not use it as the axis.
        quiet = [self.review(1.0), self.review(5.0), self.review(3.0)]
        loud = [self.review(1.0, 100), self.review(5.0), self.review(3.0)]
        self.assertLess(peer_spread(loud, SIMPLE), peer_spread(quiet, SIMPLE))

    def test_empty(self):
        self.assertEqual(peer_spread([], SIMPLE), 0.0)
        self.assertEqual(review_spread([]), 0.0)


if __name__ == "__main__":
    unittest.main()
