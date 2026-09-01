import unittest

from app_control.app_confidence import decide_app_open_action


class AppConfidenceTests(unittest.TestCase):
    def test_low_confidence_asks_for_rephrase(self):
        decision = decide_app_open_action(0.69, confirm_before_open=False)

        self.assertTrue(decision.should_rephrase)

    def test_medium_confidence_forces_confirmation(self):
        decision = decide_app_open_action(0.70, confirm_before_open=False)

        self.assertTrue(decision.should_confirm)

    def test_high_confidence_respects_confirmation_setting(self):
        confirm = decide_app_open_action(0.90, confirm_before_open=True)
        open_directly = decide_app_open_action(0.90, confirm_before_open=False)

        self.assertTrue(confirm.should_confirm)
        self.assertTrue(open_directly.should_open)


if __name__ == "__main__":
    unittest.main()
