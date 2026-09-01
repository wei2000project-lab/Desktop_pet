import unittest
from datetime import datetime

from app_control.app_schedule import parse_schedule_delay


class AppScheduleTests(unittest.TestCase):
    def test_parse_minutes_after_request(self):
        delay = parse_schedule_delay("幫我在5分鐘後開啟 Chrome", now=datetime(2026, 6, 28, 12, 0, 0))

        self.assertEqual(delay.seconds, 300)
        self.assertEqual(delay.label, "5 分鐘後")
        self.assertEqual(delay.run_at, datetime(2026, 6, 28, 12, 5, 0))

    def test_parse_half_width_space_minutes_after_request(self):
        delay = parse_schedule_delay("幫我在 10 分鐘後開啟 Chrome", now=datetime(2026, 6, 28, 12, 0, 0))

        self.assertEqual(delay.seconds, 600)
        self.assertEqual(delay.label, "10 分鐘後")

    def test_non_schedule_request_returns_none(self):
        self.assertIsNone(parse_schedule_delay("幫我開啟 Chrome"))

    def test_parse_absolute_time_request_today(self):
        delay = parse_schedule_delay("幫我在9:50開啟 Chrome", now=datetime(2026, 6, 28, 9, 40, 0))

        self.assertEqual(delay.seconds, 600)
        self.assertEqual(delay.label, "09:50")
        self.assertEqual(delay.run_at, datetime(2026, 6, 28, 9, 50, 0))

    def test_absolute_time_request_returns_none_when_time_already_passed(self):
        delay = parse_schedule_delay("幫我在9:50開啟 Chrome", now=datetime(2026, 6, 28, 9, 51, 0))

        self.assertIsNone(delay)


if __name__ == "__main__":
    unittest.main()
