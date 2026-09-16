import pathlib
import unittest

from ui.pet.bubble import ChatBubble


class ChatCancelSourceTests(unittest.TestCase):
    def test_bubble_send_button_switches_to_stop_during_ai_response(self):
        source = pathlib.Path("ui/pet/bubble.py").read_text(encoding="utf-8")

        self.assertIn('self.send_btn = QPushButton("送出"', source)
        self.assertIn('self.send_btn.setText("停止")', source)
        self.assertIn('self.send_btn.setText("送出")', source)
        self.assertIn('"chat_response_cancel_requested"', source)
        self.assertIn('"ai_message_cancelled"', source)

    def test_conversation_manager_subscribes_to_cancel_event(self):
        source = pathlib.Path("app/ai/conversation_manager.py").read_text(encoding="utf-8")

        self.assertIn('"chat_response_cancel_requested"', source)
        self.assertIn("handle_cancel_requested", source)
        self.assertIn("self.provider.cancel()", source)
        self.assertIn('"ai_message_cancelled"', source)

    def test_scheduled_notifications_do_not_change_active_ai_state(self):
        source = pathlib.Path("ui/pet/bubble.py").read_text(encoding="utf-8")

        self.assertIn('"chat_system_notification"', source)
        self.assertIn("pending_system_notifications", source)
        self.assertIn("def on_system_notification", source)
        self.assertIn("def _flush_system_notifications", source)

    def test_system_notification_waits_for_active_ai_turn(self):
        class BubbleState:
            is_waiting_response = True
            pending_system_notifications = []
            appended = []

            def _append_system_notification(self, message, is_error):
                self.appended.append((message, is_error))

        bubble = BubbleState()

        ChatBubble.on_system_notification(bubble, "排程時間到", False)

        self.assertTrue(bubble.is_waiting_response)
        self.assertEqual(bubble.pending_system_notifications, [("排程時間到", False)])
        self.assertEqual(bubble.appended, [])

        bubble.is_waiting_response = False
        ChatBubble._flush_system_notifications(bubble)

        self.assertEqual(bubble.pending_system_notifications, [])
        self.assertEqual(bubble.appended, [("排程時間到", False)])

    def test_provider_and_client_have_cancel_hooks(self):
        provider_source = pathlib.Path("app/ai/provider.py").read_text(encoding="utf-8")
        client_source = pathlib.Path("app/ai/client.py").read_text(encoding="utf-8")

        self.assertIn("def cancel", provider_source)
        self.assertIn("should_cancel", provider_source)
        self.assertIn("def cancel", client_source)
        self.assertIn("_raise_if_cancelled", client_source)


if __name__ == "__main__":
    unittest.main()
