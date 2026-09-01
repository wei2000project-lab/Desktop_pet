from PySide6.QtWidgets import QInputDialog

from core.event_bus import event_bus


class AppPreferenceChoice:
    def __init__(self, bus=event_bus):
        self.bus = bus
        self.bus.subscribe("app_preference_choice_requested", self.choose_preferred_app)

    def choose_preferred_app(self, preference_key: str, choices: tuple[str, ...], reason: str):
        if not choices:
            self.bus.publish("app_preference_choice_cancelled", preference_key)
            return

        message = "這類需求之後要優先使用哪個應用程式？"
        if reason:
            message += f"\n\n原因：{reason}"

        app_name, accepted = QInputDialog.getItem(
            None,
            "選擇偏好應用程式",
            message,
            list(choices),
            0,
            False,
        )

        if accepted and app_name:
            self.bus.publish("app_preference_chosen", preference_key, app_name)
            return

        self.bus.publish("app_preference_choice_cancelled", preference_key)
