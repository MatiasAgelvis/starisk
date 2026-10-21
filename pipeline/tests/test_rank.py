import unittest

from stellaid.rank import average_ranks, spearman


class RankTest(unittest.TestCase):
    def test_average_ranks_assigns_one_based_average_ranks(self):
        self.assertEqual(average_ranks([10, 20, 30]), [1, 2, 3])
        self.assertEqual(average_ranks([30, 10, 20]), [3, 1, 2])
        # two values tie for ranks 1 and 2 -> both get 1.5
        self.assertEqual(average_ranks([5, 5, 9]), [1.5, 1.5, 3])

    def test_spearman_is_one_for_identical_orderings(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]), 1.0)

    def test_spearman_is_minus_one_for_reversed_orderings(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0)

    def test_spearman_matches_a_known_value(self):
        # ranks [1,2,3,4,5] vs [2,1,4,3,5] -> 0.8
        self.assertAlmostEqual(spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]), 0.8)


if __name__ == "__main__":
    unittest.main()
