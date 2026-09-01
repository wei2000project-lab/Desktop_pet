import pathlib
import unittest


class ChatCancelSourceTests(unittest.TestCase):
    def test_bubble_send_button_switches_to_stop_during_ai_response(self):
        source = pathlib.Path("ui/bubble.py").read_text(encoding="utf-8")

        self.assertIn('self.send_btn = QPushButton("送出"', source)
        self.assertIn('self.send_btn.setText("停止")', source)
        self.assertIn('self.send_btn.setText("送出")', source)
        self.assertIn('"chat_response_cancel_requested"', source)
        self.assertIn('"ai_message_cancelled"', source)

    def test_conversation_manager_subscribes_to_cancel_event(self):
        source = pathlib.Path("ai/conversation_manager.py").read_text(encoding="utf-8")

        self.assertIn('"chat_response_cancel_requested"', source)
        self.assertIn("handle_cancel_requested", source)
        self.assertIn("self.provider.cancel()", source)
        self.assertIn('"ai_message_cancelled"', source)

    def test_provider_and_client_have_cancel_hooks(self):
        provider_source = pathlib.Path("ai/provider.py").read_text(encoding="utf-8")
        client_source = pathlib.Path("ai/client.py").read_text(encoding="utf-8")

        self.assertIn("def cancel", provider_source)
        self.assertIn("should_cancel", provider_source)
        self.assertIn("def cancel", client_source)
        self.assertIn("_raise_if_cancelled", client_source)


if __name__ == "__main__":
    unittest.main()
