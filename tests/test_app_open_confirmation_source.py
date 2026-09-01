import pathlib
import unittest


class AppOpenConfirmationSourceTests(unittest.TestCase):
    def test_confirmation_ui_subscribes_to_confirmation_event(self):
        source = pathlib.Path("ui/app_open_confirmation.py").read_text(encoding="utf-8")

        self.assertIn("app_open_confirmation_requested", source)
        self.assertIn("app_open_confirmed", source)
        self.assertIn("app_open_cancelled", source)
        self.assertIn("QMessageBox.question", source)

    def test_main_initializes_confirmation_ui(self):
        source = pathlib.Path("main.py").read_text(encoding="utf-8")

        self.assertIn("AppOpenConfirmation", source)


if __name__ == "__main__":
    unittest.main()
