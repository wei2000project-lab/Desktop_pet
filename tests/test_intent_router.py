import unittest

from intent.intent_router import IntentType, route_intent
from intent.user_message_router import UserMessageRouter
from app_control.app_open_request_handler import AppOpenRequestHandler


class FakeEventBus:
    def __init__(self):
        self.subscriptions = {}
        self.published = []

    def subscribe(self, event_type, callback):
        self.subscriptions[event_type] = callback

    def publish(self, event_type, *args, **kwargs):
        self.published.append((event_type, args, kwargs))


class IntentRouterTests(unittest.TestCase):
    def test_routes_regular_message_to_chat(self):
        intent = route_intent("今天心情不太好")

        self.assertEqual(intent.type, IntentType.CHAT)
        self.assertEqual(intent.text, "今天心情不太好")

    def test_routes_explicit_open_app_request(self):
        intent = route_intent("幫我打開 Chrome")

        self.assertEqual(intent.type, IntentType.OPEN_APP)
        self.assertEqual(intent.text, "幫我打開 Chrome")

    def test_routes_goal_like_app_request(self):
        intent = route_intent("我要上網")

        self.assertEqual(intent.type, IntentType.OPEN_APP)

    def test_routes_preference_change_request(self):
        intent = route_intent("更改搜尋偏好")

        self.assertEqual(intent.type, IntentType.APP_PREFERENCE_CHANGE)
        self.assertEqual(intent.text, "更改搜尋偏好")

    def test_user_message_router_publishes_chat_event(self):
        bus = FakeEventBus()
        UserMessageRouter(bus)

        bus.subscriptions["user_message_sent"]("你好")

        self.assertEqual(bus.published, [("chat_message_requested", ("你好",), {})])

    def test_user_message_router_publishes_app_open_event(self):
        bus = FakeEventBus()
        UserMessageRouter(bus)

        bus.subscriptions["user_message_sent"]("幫我打開 Chrome")

        self.assertEqual(bus.published, [("app_open_requested", ("幫我打開 Chrome",), {})])

    def test_user_message_router_publishes_preference_change_event(self):
        bus = FakeEventBus()
        UserMessageRouter(bus)

        bus.subscriptions["user_message_sent"]("更改搜尋偏好")

        self.assertEqual(bus.published, [("app_preference_change_requested", ("更改搜尋偏好",), {})])

    def test_app_open_request_handler_subscribes_to_app_events(self):
        bus = FakeEventBus()
        AppOpenRequestHandler(bus)

        self.assertIn("app_open_requested", bus.subscriptions)
        self.assertIn("app_open_confirmed", bus.subscriptions)
        self.assertIn("app_open_cancelled", bus.subscriptions)


if __name__ == "__main__":
    unittest.main()
