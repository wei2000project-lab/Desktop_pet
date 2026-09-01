import pathlib
import unittest


class RoutingSourceTests(unittest.TestCase):
    def test_conversation_manager_uses_routed_chat_event(self):
        source = pathlib.Path("ai/conversation_manager.py").read_text(encoding="utf-8")

        self.assertIn("chat_message_requested", source)
        self.assertNotIn('"user_message_sent"', source)

    def test_main_initializes_user_message_router(self):
        source = pathlib.Path("main.py").read_text(encoding="utf-8")

        self.assertIn("UserMessageRouter(event_bus)", source)
        self.assertIn("AppOpenRequestHandler(event_bus)", source)


if __name__ == "__main__":
    unittest.main()
