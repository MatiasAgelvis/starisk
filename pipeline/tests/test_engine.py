import unittest

from stellaid.engine import DEFAULTS, SIMPLE, course_score, peer_score, review_weight


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


if __name__ == "__main__":
    unittest.main()
