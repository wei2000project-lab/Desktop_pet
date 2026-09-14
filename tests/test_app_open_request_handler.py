import unittest
from datetime import datetime, timedelta

from app.control.execution.launcher import AppLaunchResult
from app.control.execution.request_handler import AppOpenRequestHandler
from app.control.resolution.selector import AppSelection


class FakeEventBus:
    def __init__(self):
        self.subscriptions = {}
        self.published = []

    def subscribe(self, event_type, callback):
        self.subscriptions[event_type] = callback

    def publish(self, event_type, *args, **kwargs):
        self.published.append((event_type, args, kwargs))


class FakeSelector:
    def __init__(self, selection):
        self.selection = selection


class FakeService:
    def __init__(self, selection, launch_result=None, preference_change_selection=None):
        self.selector = None
        self.opened_app_name = ""
        self.selection = selection
        self.preference_change_text = ""
        self.preference_change_selection = preference_change_selection or selection
        self.launch_result = launch_result or AppLaunchResult(success=True, app_name="Google Chrome", path="x")
        self.preferences = {}
        self.background_refresh_count = 0

    def refresh_index_in_background(self):
        self.background_refresh_count += 1
        return True

    def select_app_from_text(self, user_text, selector):
        self.selector = selector
        return self.selection

    def open_app_by_name(self, app_name):
        self.opened_app_name = app_name
        return self.launch_result

    def select_preference_change_from_text(self, user_text):
        self.preference_change_text = user_text
        return self.preference_change_selection

    def remember_preferred_app(self, preference_key, app_name):
        self.preferences[preference_key] = app_name


class FakeScheduler:
    def __init__(self):
        self.scheduled = []

    def schedule(self, delay_seconds, callback):
        self.scheduled.append((delay_seconds, callback))


class AppOpenRequestHandlerTests(unittest.TestCase):
    def test_app_started_refreshes_index_in_background(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            run_in_background=False,
        )

        bus.subscriptions["app_started"]()

        self.assertEqual(service.background_refresh_count, 1)

    def test_successful_selection_requests_confirmation(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("我要上網")

        self.assertEqual(bus.published[0][0], "ai_message_started")
        self.assertEqual(bus.published[1], ("app_open_confirmation_requested", ("Google Chrome", "上網", 0.95), {}))
        self.assertEqual(service.opened_app_name, "")

    def test_confirmed_app_opens_through_service(self):
        bus = FakeEventBus()
        service = FakeService(AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網"))
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_confirmed"]("Google Chrome")

        self.assertEqual(service.opened_app_name, "Google Chrome")
        self.assertEqual(bus.published[0][0], "ai_message_chunk")
        self.assertIn("已開啟 Google Chrome", bus.published[0][1][0])

    def test_cancelled_windows_launch_finishes_the_chat_turn(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Roblox", confidence=0.95, reason="遊戲"),
            launch_result=AppLaunchResult(
                success=False,
                app_name="Roblox",
                path="Roblox.lnk",
                error="launch_cancelled",
            ),
        )
        AppOpenRequestHandler(bus=bus, service=service, selector=FakeSelector(None), run_in_background=False)

        bus.subscriptions["app_open_confirmed"]("Roblox")

        self.assertIn(("ai_message_chunk", ("已取消開啟 Roblox。",), {}), bus.published)
        self.assertIn(("ai_message_finished", ("",), {}), bus.published)
        self.assertNotIn("ai_message_error", [event[0] for event in bus.published])

    def test_unexpected_launch_error_resets_the_chat_with_an_error(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Roblox", confidence=0.95, reason="遊戲")
        )

        def raise_launch_error(app_name):
            raise RuntimeError("boom")

        service.open_app_by_name = raise_launch_error
        AppOpenRequestHandler(bus=bus, service=service, selector=FakeSelector(None), run_in_background=False)

        bus.subscriptions["app_open_confirmed"]("Roblox")

        error_events = [event for event in bus.published if event[0] == "ai_message_error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("無法開啟 Roblox", error_events[0][1][0])

    def test_can_open_without_confirmation_when_disabled(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=False,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("我要上網")

        self.assertEqual(service.opened_app_name, "Google Chrome")
        self.assertNotIn("app_open_confirmation_requested", [event[0] for event in bus.published])

    def test_scheduled_open_request_asks_for_schedule_confirmation(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        scheduler = FakeScheduler()
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=False,
            run_in_background=False,
            scheduler=scheduler,
        )

        bus.subscriptions["app_open_requested"]("幫我在5分鐘後開啟 Chrome")

        self.assertEqual(service.opened_app_name, "")
        self.assertEqual(scheduler.scheduled, [])
        self.assertEqual(
            bus.published[1][0],
            "app_scheduled_open_confirmation_requested",
        )
        self.assertEqual(bus.published[1][1][0], "Google Chrome")
        self.assertEqual(bus.published[1][1][1], 300)
        self.assertIn("5 分鐘後", bus.published[1][1][2])

    def test_confirmed_scheduled_open_runs_later_without_second_confirmation(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        scheduler = FakeScheduler()
        requested_at = datetime(2026, 9, 13, 10, 0, 0)
        now_values = [requested_at, requested_at + timedelta(milliseconds=100)]

        def fake_now():
            return now_values.pop(0)

        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
            scheduler=scheduler,
            now_fn=fake_now,
        )

        bus.subscriptions["app_open_requested"]("幫我在5分鐘後開啟 Chrome")
        bus.subscriptions["app_scheduled_open_confirmed"]("Google Chrome", 300)

        self.assertEqual(service.opened_app_name, "")
        self.assertEqual(len(scheduler.scheduled), 1)
        self.assertEqual(scheduler.scheduled[0][0], 300)

        scheduler.scheduled[0][1]()

        self.assertEqual(service.opened_app_name, "Google Chrome")
        event_names = [event[0] for event in bus.published]
        self.assertNotIn("app_open_confirmation_requested", event_names)

    def test_scheduled_open_uses_system_notification_without_finishing_active_ai_turn(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        handler = AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            run_in_background=False,
        )

        handler._open_scheduled_app("Google Chrome")

        self.assertEqual(
            bus.published,
            [("chat_system_notification", ("排程時間到，已開啟 Google Chrome。", False), {})],
        )
        self.assertNotIn("ai_message_finished", [event[0] for event in bus.published])

    def test_scheduled_launch_failure_uses_error_notification(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Roblox", confidence=0.95, reason="遊戲"),
            launch_result=AppLaunchResult(
                success=False,
                app_name="Roblox",
                path="Roblox.lnk",
                error="launch_failed",
            ),
        )
        handler = AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            run_in_background=False,
        )

        handler._open_scheduled_app("Roblox")

        self.assertEqual(bus.published[0][0], "chat_system_notification")
        self.assertIn("無法開啟 Roblox", bus.published[0][1][0])
        self.assertTrue(bus.published[0][1][1])
        self.assertNotIn("ai_message_error", [event[0] for event in bus.published])

    def test_confirmed_scheduled_open_does_not_schedule_when_target_time_already_passed(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.95, reason="上網")
        )
        scheduler = FakeScheduler()
        now_values = [
            __import__("datetime").datetime(2026, 6, 28, 9, 40, 0),
            __import__("datetime").datetime(2026, 6, 28, 9, 51, 0),
        ]

        def fake_now():
            return now_values.pop(0)

        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
            scheduler=scheduler,
            now_fn=fake_now,
        )

        bus.subscriptions["app_open_requested"]("幫我在9:50開啟 Chrome")
        bus.subscriptions["app_scheduled_open_confirmed"]("Google Chrome", 600)

        self.assertEqual(scheduler.scheduled, [])
        self.assertEqual(service.opened_app_name, "")
        error_events = [event for event in bus.published if event[0] == "ai_message_error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("排程時間已經過了", error_events[0][1][0])

    def test_medium_confidence_selection_requests_confirmation_even_when_disabled(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="open_app", app_name="Google Chrome", confidence=0.75, reason="可能是上網")
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=False,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("幫我開那個查東西的")

        self.assertEqual(service.opened_app_name, "")
        self.assertEqual(
            bus.published[1],
            ("app_open_confirmation_requested", ("Google Chrome", "可能是上網", 0.75), {}),
        )

    def test_selection_error_is_reported_to_chat(self):
        bus = FakeEventBus()
        service = FakeService(AppSelection(action="none", app_name="", confidence=0, reason="", error="empty_app_index"))
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("我要上網")

        event_names = [event[0] for event in bus.published]
        self.assertIn("ai_message_error", event_names)

    def test_low_confidence_selection_asks_user_to_rephrase(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(
                action="none",
                app_name="Google Chrome",
                confidence=0.61,
                reason="不確定",
                error="low_confidence",
            )
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("幫我開那個")

        error_events = [event for event in bus.published if event[0] == "ai_message_error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("不太確定", error_events[0][1][0])

    def test_requested_uninstalled_app_error_is_specific(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(
                action="none",
                app_name="discord",
                confidence=0,
                reason="使用者指定的應用程式不在本機清單中",
                error="requested_app_not_installed",
            )
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("幫我開啟 Discord")

        error_events = [event for event in bus.published if event[0] == "ai_message_error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("找不到", error_events[0][1][0])

    def test_app_choice_required_requests_preference_choice(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(
                action="none",
                app_name="",
                confidence=0,
                reason="使用者需要瀏覽工具",
                error="app_choice_required",
                preference_key="browser",
                choices=("Google Chrome", "Microsoft Edge"),
            )
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_open_requested"]("幫我開瀏覽工具")

        self.assertEqual(
            bus.published[1],
            (
                "app_preference_choice_requested",
                ("browser", ("Google Chrome", "Microsoft Edge"), "使用者需要瀏覽工具"),
                {},
            ),
        )

    def test_preference_change_request_prompts_choice(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="none", app_name="", confidence=0, reason="", error="empty_app_index"),
            preference_change_selection=AppSelection(
                action="none",
                app_name="",
                confidence=0,
                reason="使用者需要查詢或上網工具",
                error="app_choice_required",
                preference_key="browser",
                choices=("Google Chrome", "Microsoft Edge"),
            ),
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_preference_change_requested"]("更改搜尋偏好")

        self.assertEqual(service.preference_change_text, "更改搜尋偏好")
        self.assertEqual(
            bus.published[1],
            (
                "app_preference_choice_requested",
                ("browser", ("Google Chrome", "Microsoft Edge"), "使用者需要查詢或上網工具"),
                {},
            ),
        )

    def test_chosen_preference_is_saved_then_confirmation_is_requested(self):
        bus = FakeEventBus()
        service = FakeService(AppSelection(action="none", app_name="", confidence=0, reason="", error="empty_app_index"))
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_preference_chosen"]("browser", "Microsoft Edge")

        self.assertEqual(service.preferences, {"browser": "Microsoft Edge"})
        self.assertEqual(
            bus.published[0],
            ("app_open_confirmation_requested", ("Microsoft Edge", "已記住你的偏好", 1.0), {}),
        )

    def test_chosen_preference_from_change_request_is_saved_without_opening(self):
        bus = FakeEventBus()
        service = FakeService(
            AppSelection(action="none", app_name="", confidence=0, reason="", error="empty_app_index"),
            preference_change_selection=AppSelection(
                action="none",
                app_name="",
                confidence=0,
                reason="使用者需要查詢或上網工具",
                error="app_choice_required",
                preference_key="browser",
                choices=("Google Chrome", "Microsoft Edge"),
            ),
        )
        AppOpenRequestHandler(
            bus=bus,
            service=service,
            selector=FakeSelector(None),
            confirm_before_open=True,
            run_in_background=False,
        )

        bus.subscriptions["app_preference_change_requested"]("更改搜尋偏好")
        bus.subscriptions["app_preference_chosen"]("browser", "Microsoft Edge")

        self.assertEqual(service.preferences, {"browser": "Microsoft Edge"})
        self.assertEqual(service.opened_app_name, "")
        event_names = [event[0] for event in bus.published]
        self.assertNotIn("app_open_confirmation_requested", event_names)
        self.assertIn(("ai_message_chunk", ("已將搜尋偏好改為 Microsoft Edge。",), {}), bus.published)


if __name__ == "__main__":
    unittest.main()
