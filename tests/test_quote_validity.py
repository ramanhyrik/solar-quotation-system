import unittest
from datetime import datetime, timezone

from quote_validity import quote_valid_until


class QuoteValidityTests(unittest.TestCase):
    def test_fourteen_business_days_from_screenshot_date(self):
        self.assertEqual(
            quote_valid_until(datetime(2026, 9, 22)), datetime(2026, 10, 12)
        )

    def test_skips_public_holidays_as_well_as_weekends(self):
        # Rosh Hashanah (Sep 13) and Yom Kippur (Sep 21) are not counted.
        self.assertEqual(
            quote_valid_until(datetime(2026, 9, 10)), datetime(2026, 10, 4)
        )

    def test_counts_sunday_but_not_issue_date(self):
        self.assertEqual(
            quote_valid_until(datetime(2026, 1, 4)), datetime(2026, 1, 22)
        )

    def test_weekend_issue_dates(self):
        for day in (9, 10):  # Friday and Saturday
            with self.subTest(day=day):
                self.assertEqual(
                    quote_valid_until(datetime(2026, 1, day)), datetime(2026, 1, 28)
                )

    def test_year_boundary_and_time_are_preserved(self):
        self.assertEqual(
            quote_valid_until(datetime(2026, 12, 24, 15, 30, tzinfo=timezone.utc)),
            datetime(2027, 1, 13, 15, 30, tzinfo=timezone.utc),
        )

    def test_leap_day(self):
        self.assertEqual(
            quote_valid_until(datetime(2028, 2, 17)), datetime(2028, 3, 8)
        )


if __name__ == "__main__":
    unittest.main()
