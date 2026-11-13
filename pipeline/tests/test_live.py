"""The checks in `smoke.py`, against the real pages.

Skipped by default: these need the network and the live site, and a unit suite
that fails when Coursera is slow is a unit suite people learn to ignore.

    STARISK_LIVE=1 python3 -m unittest tests.test_live

`nightly.py` runs the same functions before the crawl.
"""

import os
import unittest

from starisk import smoke

LIVE = os.environ.get("STARISK_LIVE") == "1"


@unittest.skipUnless(LIVE, "live checks: set STARISK_LIVE=1")
class LiveAdapterTest(unittest.TestCase):
    def test_a_normal_course_still_parses(self):
        self.assertEqual(smoke.check_course(), [])

    def test_a_low_sample_course_still_parses(self):
        self.assertEqual(smoke.check_course(smoke.LOW_SAMPLE_KEY), [])

    def test_the_landing_page_still_carries_title_and_provider(self):
        self.assertEqual(smoke.check_landing(), [])

    def test_a_program_page_still_lists_courses(self):
        self.assertEqual(smoke.check_program(), [])


@unittest.skipUnless(LIVE, "live checks: set STARISK_LIVE=1")
class LiveSiteTest(unittest.TestCase):
    def test_the_deployed_data_is_cross_origin_readable(self):
        self.assertEqual(smoke.check_site(), [])


if __name__ == "__main__":
    unittest.main()
