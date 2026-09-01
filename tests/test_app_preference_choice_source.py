import pathlib
import unittest


class AppPreferenceChoiceSourceTests(unittest.TestCase):
    def test_preference_choice_ui_subscribes_and_publishes_choice_events(self):
        source = pathlib.Path("ui/app_preference_choice.py").read_text(encoding="utf-8")

        self.assertIn("app_preference_choice_requested", source)
        self.assertIn("app_preference_chosen", source)
        self.assertIn("app_preference_choice_cancelled", source)
        self.assertIn("QInputDialog.getItem", source)

    def test_main_initializes_preference_choice_ui(self):
        source = pathlib.Path("main.py").read_text(encoding="utf-8")

        self.assertIn("AppPreferenceChoice", source)


if __name__ == "__main__":
    unittest.main()
