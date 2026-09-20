import math
import threading
from datetime import datetime

from app.control.resolution.confidence import decide_app_open_action
from app.control.execution.service import AppOpenService, default_app_index_path
from app.control.execution.schedule import AppOpenScheduler, parse_schedule_delay
from app.control.resolution.selector import AppSelector
from app.utils.logger import logger


class AppOpenRequestHandler:
    def __init__(
        self,
        bus=None,
        service=None,
        selector=None,
        confirm_before_open=None,
        run_in_background: bool = True,
        scheduler=None,
        now_fn=None,
    ):
        if bus is None:
            from app.core.event_bus import event_bus
            bus = event_bus

        self.bus = bus
        self.service = service or AppOpenService(default_app_index_path())
        self.selector = selector or AppSelector(
            _complete_with_ai_client,
            preference_store=getattr(self.service, "preference_store", None),
        )
        self.confirm_before_open = confirm_before_open
        self.run_in_background = run_in_background
        self.scheduler = scheduler or AppOpenScheduler()
        self.now_fn = now_fn or datetime.now
        self.pending_scheduled_opens = {}
        self.pending_preference_changes = set()

        self.bus.subscribe("app_open_requested", self.handle_app_open_requested)
        self.bus.subscribe("app_preference_change_requested", self.handle_app_preference_change_requested)
        self.bus.subscribe("app_open_confirmed", self.handle_app_open_confirmed)
        self.bus.subscribe("app_open_cancelled", self.handle_app_open_cancelled)
        self.bus.subscribe("app_scheduled_open_confirmed", self.handle_scheduled_open_confirmed)
        self.bus.subscribe("app_scheduled_open_cancelled", self.handle_scheduled_open_cancelled)
        self.bus.subscribe("app_preference_chosen", self.handle_app_preference_chosen)
        self.bus.subscribe("app_preference_choice_cancelled", self.handle_app_preference_choice_cancelled)
        self.bus.subscribe("app_started", self.handle_app_started)

    def handle_app_started(self):
        self.service.refresh_index_in_background()

    def handle_app_open_requested(self, user_text: str):
        self.bus.publish("ai_message_started")
        if self.run_in_background:
            threading.Thread(
                target=self._select_and_continue,
                args=(user_text,),
                daemon=True,
                name="AppOpenRequestThread",
            ).start()
            return

        self._select_and_continue(user_text)

    def handle_app_preference_change_requested(self, user_text: str):
        self.bus.publish("ai_message_started")
        if self.run_in_background:
            threading.Thread(
                target=self._select_preference_change_and_continue,
                args=(user_text,),
                daemon=True,
                name="AppPreferenceChangeThread",
            ).start()
            return

        self._select_preference_change_and_continue(user_text)

    def _select_preference_change_and_continue(self, user_text: str):
        try:
            selection = self.service.select_preference_change_from_text(user_text)
        except Exception as exc:
            self.bus.publish("ai_message_error", f"選擇偏好類別時發生錯誤：{exc}")
            return

        if selection.error == "app_choice_required":
            self.pending_preference_changes.add(selection.preference_key)
            self.bus.publish(
                "app_preference_choice_requested",
                selection.preference_key,
                selection.choices,
                selection.reason,
            )
            return

        self.bus.publish("ai_message_error", _selection_error_message(selection.error))

    def handle_app_open_confirmed(self, app_name: str):
        try:
            result = self.service.open_app_by_name(app_name)
        except Exception as exc:
            logger.error(f"Unexpected error while opening {app_name}: {exc}", exc_info=True)
            self.bus.publish("ai_message_error", f"無法開啟 {app_name}：發生未預期的錯誤。")
            return

        if result.success:
            self.bus.publish("ai_message_chunk", f"已開啟 {result.app_name}。")
            self.bus.publish("ai_message_finished", "")
            return

        if result.error == "launch_cancelled":
            self.bus.publish("ai_message_chunk", _launch_error_message(result.error, result.app_name))
            self.bus.publish("ai_message_finished", "")
            return

        self.bus.publish("ai_message_error", _launch_error_message(result.error, result.app_name))

    def handle_app_open_cancelled(self, app_name: str):
        self.bus.publish("ai_message_chunk", f"已取消開啟 {app_name}。")
        self.bus.publish("ai_message_finished", "")

    def handle_scheduled_open_confirmed(self, app_name: str, delay_seconds: int):
        pending = self.pending_scheduled_opens.pop((app_name, delay_seconds), None)
        if not pending:
            self.bus.publish("ai_message_error", f"找不到 {app_name} 的排程開啟請求。")
            return

        remaining_seconds = math.ceil((pending["run_at"] - self.now_fn()).total_seconds())
        if remaining_seconds <= 0:
            self.bus.publish("ai_message_error", f"{app_name} 的排程時間已經過了，已取消開啟。")
            return

        self.scheduler.schedule(remaining_seconds, lambda: self._open_scheduled_app(app_name))
        self.bus.publish("ai_message_chunk", f"已排程，會在{pending['label']}開啟 {app_name}。")
        self.bus.publish("ai_message_finished", "")

    def handle_scheduled_open_cancelled(self, app_name: str, delay_seconds: int):
        self.pending_scheduled_opens.pop((app_name, delay_seconds), None)
        self.bus.publish("ai_message_chunk", f"已取消排程開啟 {app_name}。")
        self.bus.publish("ai_message_finished", "")

    def handle_app_preference_chosen(self, preference_key: str, app_name: str):
        self.service.remember_preferred_app(preference_key, app_name)
        if preference_key in self.pending_preference_changes:
            self.pending_preference_changes.discard(preference_key)
            self.bus.publish(
                "ai_message_chunk",
                f"已將{_preference_label(preference_key)}偏好改為 {app_name}。",
            )
            self.bus.publish("ai_message_finished", "")
            return

        if self._should_confirm_before_open():
            self.bus.publish("app_open_confirmation_requested", app_name, "已記住你的偏好", 1.0)
            return

        self.handle_app_open_confirmed(app_name)

    def handle_app_preference_choice_cancelled(self, preference_key: str):
        self.pending_preference_changes.discard(preference_key)
        self.bus.publish("ai_message_chunk", "已取消選擇偏好。")
        self.bus.publish("ai_message_finished", "")

    def _select_and_continue(self, user_text: str):
        schedule_delay = parse_schedule_delay(user_text, now=self.now_fn())
        try:
            selection = self.service.select_app_from_text(user_text, self.selector)
        except Exception as exc:
            self.bus.publish("ai_message_error", f"選擇應用程式時發生錯誤：{exc}")
            return

        if not selection.success:
            if selection.error == "app_choice_required":
                self.bus.publish(
                    "app_preference_choice_requested",
                    selection.preference_key,
                    selection.choices,
                    selection.reason,
                )
                return
            self.bus.publish("ai_message_error", _selection_error_message(selection.error))
            return

        decision = decide_app_open_action(selection.confidence, self._should_confirm_before_open())
        if decision.should_rephrase:
            self.bus.publish("ai_message_error", _selection_error_message("low_confidence"))
            return

        if schedule_delay:
            self.pending_scheduled_opens[(selection.app_name, schedule_delay.seconds)] = {
                "label": schedule_delay.label,
                "run_at": schedule_delay.run_at,
            }
            self.bus.publish(
                "app_scheduled_open_confirmation_requested",
                selection.app_name,
                schedule_delay.seconds,
                f"要在{schedule_delay.label}開啟 {selection.app_name} 嗎？",
                schedule_delay.run_at,
            )
            return

        if decision.should_confirm:
            self.bus.publish(
                "app_open_confirmation_requested",
                selection.app_name,
                selection.reason,
                selection.confidence,
            )
            return

        self.handle_app_open_confirmed(selection.app_name)

    def _open_scheduled_app(self, app_name: str):
        try:
            result = self.service.open_app_by_name(app_name)
        except Exception as exc:
            logger.error(f"Unexpected error while opening scheduled app {app_name}: {exc}", exc_info=True)
            self.bus.publish(
                "chat_system_notification",
                f"排程時間到，但無法開啟 {app_name}：發生未預期的錯誤。",
                True,
            )
            return

        if result.success:
            self.bus.publish("chat_system_notification", f"排程時間到，已開啟 {result.app_name}。", False)
            return

        message = _launch_error_message(result.error, result.app_name)
        message = f"排程時間到，但{message}"
        self.bus.publish("chat_system_notification", message, result.error != "launch_cancelled")

    def _should_confirm_before_open(self) -> bool:
        if self.confirm_before_open is not None:
            return bool(self.confirm_before_open)

        try:
            from app.core.config_manager import config_manager
            return config_manager.get_general_bool("ConfirmBeforeOpen", True)
        except Exception:
            return True


def _complete_with_ai_client(messages):
    from app.ai.request_executor import AIRequestExecutor, RequestExecutionLimits
    from app.settings import APIGroupService

    snapshot = APIGroupService().resolve_runtime_request()
    executor = AIRequestExecutor(
        limits=RequestExecutionLimits(operation_timeout=30.0)
    )
    return executor.execute(snapshot, messages, max_chars=800)


def _selection_error_message(error: str) -> str:
    messages = {
        "empty_app_index": "目前沒有可用的應用程式清單，請先重新掃描開始功能表。",
        "invalid_json": "AI 沒有回傳可解析的應用程式選擇結果。",
        "unsupported_action": "AI 回傳了不支援的動作。",
        "app_not_in_index": "AI 選到的應用程式不在本機清單中，已拒絕執行。",
        "requested_app_not_installed": "找不到你指定的應用程式，請確認是否已安裝或重新掃描應用程式清單。",
        "app_choice_required": "找到多個可用的應用程式，請先選擇偏好的工具。",
        "low_confidence": "我不太確定你想開啟哪個應用程式，可以再描述清楚一點嗎？",
    }
    return messages.get(error, f"無法選擇應用程式：{error}")


def _launch_error_message(error: str, app_name: str) -> str:
    messages = {
        "app_not_found": f"找不到應用程式：{app_name}",
        "shortcut_not_found": f"{app_name} 的捷徑不存在，請重新掃描應用程式清單。",
        "launch_cancelled": f"已取消開啟 {app_name}。",
        "launch_failed": f"無法開啟 {app_name}，請稍後再試。",
    }
    return messages.get(error, f"無法開啟 {app_name}：{error}")


def _preference_label(preference_key: str) -> str:
    labels = {
        "browser": "搜尋",
        "document": "文書",
        "chat": "聊天",
        "video": "影片播放",
    }
    return labels.get(preference_key, preference_key)
