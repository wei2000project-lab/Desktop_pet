from PySide6.QtWidgets import QMessageBox

from app.core.event_bus import event_bus


class AppOpenConfirmation:
    def __init__(self, bus=event_bus):
        self.bus = bus
        self.bus.subscribe("app_open_confirmation_requested", self.confirm_app_open)
        self.bus.subscribe("app_scheduled_open_confirmation_requested", self.confirm_scheduled_app_open)

    def confirm_app_open(self, app_name: str, reason: str, confidence: float):
        message = f"要幫你打開 {app_name} 嗎？"
        if reason:
            message += f"\n\n原因：{reason}"

        result = QMessageBox.question(
            None,
            "確認開啟應用程式",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self.bus.publish("app_open_confirmed", app_name)
            return

        self.bus.publish("app_open_cancelled", app_name)

    def confirm_scheduled_app_open(self, app_name: str, delay_seconds: int, message: str, run_at):
        if run_at:
            message += f"\n\n預計時間：{run_at.strftime('%Y-%m-%d %H:%M:%S')}"

        result = QMessageBox.question(
            None,
            "確認排程開啟應用程式",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self.bus.publish("app_scheduled_open_confirmed", app_name, delay_seconds)
            return

        self.bus.publish("app_scheduled_open_cancelled", app_name, delay_seconds)
