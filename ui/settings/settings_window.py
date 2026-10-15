"""Settings view: layout, input events, dialogs, and rendering only."""
from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import (
    QApplication, QAbstractScrollArea, QAbstractSpinBox,
    QHBoxLayout, QLabel, QPushButton, QWidget,
)

from app.contracts.settings import CloseChoice, CloseRequest, ConnectionInputs
from ui.dashboard import DashboardWindow
from ui.dashboard.page_registry import PageDefinition
from ui.settings.page_registry import default_page_definitions
from ui.settings.pages import AIPage, AppearancePage, BehaviorPage, GeneralPage, PersonalityPage
from ui.settings.dialogs import SettingsDialog
from ui.settings.widgets.input_controls import finish_input, scroll_page_with_wheel
from ui.settings.styles import SETTINGS_STYLES


class SettingsWindow(DashboardWindow):
    settings_changed = Signal(dict)
    groups_changed = Signal(object)
    apply_requested = Signal()
    cancel_requested = Signal()
    clear_history_requested = Signal()
    close_requested = Signal(object)
    closed = Signal()
    legacy_test_requested = Signal(int)
    group_test_requested = Signal(str, str)
    add_group_requested = Signal()
    add_key_requested = Signal(str)
    delete_group_requested = Signal(str)

    def __init__(self, parent=None, page_definitions: tuple[PageDefinition, ...] | None = None):
        super().__init__(
            parent,
            page_definitions=default_page_definitions() if page_definitions is None else page_definitions,
            title="Nova 設定",
        )
        self.setObjectName("settingsWindow")
        self._wheel_filter_installed = False
        self._close_approved = False
        self.general_page = self.appearance_page = self.behavior_page = None
        self.ai_page = self.personality_page = None
        for definition in self.page_definitions:
            page = self.page_for_key(definition.key)
            page.setObjectName(f"settingsPage_{definition.key}")
            page.setProperty("settingsPage", True)
            if definition.key == "general" and isinstance(page, GeneralPage):
                self.general_page = page
                page.settings_changed.connect(lambda enabled: self.settings_changed.emit({"always_on_top": enabled}))
                page.clear_history_requested.connect(self.clear_history_requested)
            elif definition.key == "appearance" and isinstance(page, AppearancePage):
                self.appearance_page = page
                page.size_changed.connect(lambda width, height: self.settings_changed.emit({"width": width, "height": height}))
            elif definition.key == "behavior" and isinstance(page, BehaviorPage):
                self.behavior_page = page
                page.reading_idle_changed.connect(lambda seconds: self.settings_changed.emit({"reading_idle_seconds": seconds}))
            elif definition.key == "ai" and isinstance(page, AIPage):
                self.ai_page = page
                page.settings_changed.connect(self.settings_changed)
                page.test_requested.connect(self.legacy_test_requested)
                page.group_editor.settings_changed.connect(self.groups_changed)
                page.group_editor.test_requested.connect(self.group_test_requested)
                page.group_editor.add_group_requested.connect(self.add_group_requested)
                page.group_editor.add_key_requested.connect(self.add_key_requested)
                page.group_editor.delete_group_requested.connect(self.delete_group_requested)
            elif definition.key == "personality" and isinstance(page, PersonalityPage):
                self.personality_page = page
                page.settings_changed.connect(lambda selected, custom: self.settings_changed.emit(
                    {"selected_personality": selected, "custom_personality": custom}))

        action_bar = QWidget()
        action_bar.setObjectName("settingsActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(24, 12, 24, 12)
        action_layout.setSpacing(10)
        self.change_status_label = QLabel()
        self.change_status_label.setObjectName("settingsChangeStatus")
        action_layout.addWidget(self.change_status_label, 1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("settingsCancelButton")
        self.cancel_button.clicked.connect(self.cancel_requested)
        action_layout.addWidget(self.cancel_button)
        self.apply_button = QPushButton("套用")
        self.apply_button.setObjectName("settingsApplyButton")
        self.apply_button.clicked.connect(self.apply_requested)
        action_layout.addWidget(self.apply_button)
        self.add_content_footer(action_bar)
        self.show_dirty_state(False)
        self.setStyleSheet(self.styleSheet() + SETTINGS_STYLES)

    def load_snapshot(self, snapshot):
        for page in (self.general_page, self.appearance_page, self.behavior_page,
                     self.ai_page, self.personality_page):
            if page is not None:
                page.load_snapshot(snapshot)

    def load_groups(self, groups, enabled, error):
        if self.ai_page is None:
            return
        page = self.ai_page
        page.set_group_mode(enabled)
        page.group_editor.setVisible(enabled)
        page.group_editor.setEnabled(error is None)
        page.group_error_label.setVisible(error is not None)
        page.group_error_label.setText(error or "")
        page.group_editor.load_settings(groups)

    def set_personality_options(self, options):
        if self.personality_page is not None:
            self.personality_page.set_options(options)

    def show_dirty_state(self, dirty):
        self.apply_button.setEnabled(dirty)
        self.change_status_label.setText("有未儲存的變更" if dirty else "沒有未儲存的變更")

    def show_saved(self):
        self.change_status_label.setText("設定已儲存")

    def commit_pending_input(self):
        for page in (self.appearance_page, self.behavior_page, self.ai_page):
            if page is not None:
                page.commit_pending_input()
        if self.ai_page is not None:
            self.ai_page.group_editor.commit_pending_input()

    def show_group_feedback(self, feedback):
        if self.ai_page is not None:
            self.ai_page.group_editor.show_feedback(feedback)

    def add_api_group(self, group):
        if self.ai_page is not None:
            self.ai_page.group_editor.add_group(group)

    def add_api_key(self, group_id, entry):
        if self.ai_page is not None:
            self.ai_page.group_editor.add_key(group_id, entry)

    def remove_api_group(self, group_id):
        if self.ai_page is not None:
            self.ai_page.group_editor.remove_group(group_id)

    def connection_inputs(self):
        if self.ai_page is None:
            return ConnectionInputs()
        return self.ai_page.connection_inputs()

    def show_test_started(self, target):
        if self.ai_page is None:
            return
        if target.kind == "legacy":
            self.ai_page.begin_test(target.row_id)
        else:
            self.ai_page.group_editor.set_test_status(target.group_id, target.key_id, "測試中…", True)

    def show_test_finished(self, target, message):
        if self.ai_page is None:
            return
        if target.kind == "legacy":
            self.ai_page.finish_test(target.row_id, message)
        else:
            self.ai_page.group_editor.set_test_status(target.group_id, target.key_id, message)

    def show_warning(self, title, message):
        SettingsDialog.warning(self, title, message)

    def confirm_clear_history(self):
        return SettingsDialog.question(
            self, "確認刪除對話紀錄", "確定要刪除所有對話紀錄嗎？這個動作無法復原。",
            SettingsDialog.Yes | SettingsDialog.No, SettingsDialog.No,
        ) == SettingsDialog.Yes

    def show_history_cleared(self):
        SettingsDialog.information(self, "已刪除", "對話紀錄已清空。")

    def confirm_group_delete(self, active):
        message = "確定刪除此群組及其金鑰嗎？"
        if active:
            message += "目前群組將變為未設定，請再選擇替代群組。"
        return SettingsDialog.question(
            self, "刪除 API 群組", message, SettingsDialog.Yes | SettingsDialog.No, SettingsDialog.No,
        ) == SettingsDialog.Yes

    def confirm_close(self):
        result = SettingsDialog.question(
            self, "尚有未儲存的變更", "要在關閉前儲存變更嗎？",
            SettingsDialog.Save | SettingsDialog.Discard | SettingsDialog.Cancel, SettingsDialog.Save,
        )
        return {SettingsDialog.Save: CloseChoice.SAVE, SettingsDialog.Discard: CloseChoice.DISCARD}.get(
            result, CloseChoice.CANCEL)

    def close_without_prompt(self):
        self._close_approved = True
        self.close()

    def closeEvent(self, event):
        request = CloseRequest()
        if not self._close_approved:
            self.close_requested.emit(request)
        event.setAccepted(request.accepted)
        if request.accepted:
            self.closed.emit()

    def showEvent(self, event) -> None:
        self._close_approved = False
        if not self._wheel_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._wheel_filter_installed = True
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if self._wheel_filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._wheel_filter_installed = False
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Wheel and self._owns_object(watched):
            focused = QApplication.focusWidget()
            if focused is not None and self._owns_object(focused):
                self._finish_wheel_input(focused)
            page = self.content_stack.currentWidget()
            if isinstance(page, QAbstractScrollArea):
                scroll_page_with_wheel(page, event)
            else:
                event.accept()
            return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _finish_wheel_input(focused):
        current = focused
        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                finish_input(current)
                return
            current = current.parent()
        finish_input(focused)
        if focused.hasFocus():
            focused.clearFocus()

    def _owns_object(self, watched):
        current = watched
        while current is not None:
            if current is self:
                return True
            current = current.parent()
        return False
