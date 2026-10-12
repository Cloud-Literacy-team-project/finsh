import unittest
from datetime import datetime, timedelta, timezone

from engine.bizday import add_bizdays, due_at, is_bizday, notify_at


class BizdayTests(unittest.TestCase):
    def test_weekday_plus_one(self):
        self.assertEqual(add_bizdays(datetime(2026, 10, 13, 15), 1), datetime(2026, 10, 14, 15))

    def test_skip_weekend(self):
        self.assertEqual(add_bizdays(datetime(2026, 10, 16, 10), 1), datetime(2026, 10, 19, 10))

    def test_skip_hangul_day_and_weekend(self):
        self.assertEqual(add_bizdays(datetime(2026, 10, 8, 9), 1), datetime(2026, 10, 12, 9))

    def test_three_business_days_from_monday(self):
        start = datetime(2026, 10, 12, 18)
        self.assertEqual(due_at(start, {"unit": "bizdays", "value": 3}), datetime(2026, 10, 15, 18))

    def test_demo_minutes(self):
        start = datetime(2026, 10, 16, 14)
        self.assertEqual(due_at(start, {"unit": "minutes", "value": 3}), datetime(2026, 10, 16, 14, 3))

    def test_holiday_and_weekend_are_not_business_days(self):
        self.assertFalse(is_bizday(datetime(2026, 10, 9)))
        self.assertFalse(is_bizday(datetime(2026, 10, 10)))

    def test_notify_one_business_day_before(self):
        due = datetime(2026, 10, 15, 18)
        self.assertEqual(notify_at(due, {"unit": "bizdays", "value": 1}), datetime(2026, 10, 14, 18))

    def test_timezone_and_time_of_day_are_preserved(self):
        kst = timezone(timedelta(hours=9))
        start = datetime(2026, 10, 8, 16, 30, tzinfo=kst)
        self.assertEqual(due_at(start, {"unit": "bizdays", "value": 1}), datetime(2026, 10, 12, 16, 30, tzinfo=kst))

    def test_bad_period_does_not_silently_choose_a_deadline(self):
        with self.assertRaises(ValueError):
            due_at(datetime(2026, 10, 12), {"unit": "bizdays", "value": -1})
        with self.assertRaises(ValueError):
            notify_at(datetime(2026, 10, 12), {"unit": "weeks", "value": 1})


if __name__ == "__main__":
    unittest.main()
