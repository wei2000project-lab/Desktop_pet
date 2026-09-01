import pathlib
import unittest


class AppOpenScheduleConfirmationSourceTests(unittest.TestCase):
    def test_confirmation_ui_subscribes_to_scheduled_open_events(self):
        source = pathlib.Path("ui/app_open_confirmation.py").read_text(encoding="utf-8")

        self.assertIn("app_scheduled_open_confirmation_requested", source)
        self.assertIn("app_scheduled_open_confirmed", source)
        self.assertIn("app_scheduled_open_cancelled", source)
        self.assertIn("確認排程開啟應用程式", source)
        self.assertIn("預計時間", source)


if __name__ == "__main__":
    unittest.main()
