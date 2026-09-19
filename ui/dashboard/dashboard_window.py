from dataclasses import replace
import os

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.settings import SettingsValidationError, settings_service
from app.settings import APIGroupService, APIGroupSettings
from app.settings.api_groups import migrate_legacy_api, validate_api_groups
from app.utils.logger import logger

from ui.dashboard.page_registry import PageDefinition, default_page_definitions
from ui.dashboard.pages import AIPage, AppearancePage, BehaviorPage, GeneralPage, PersonalityPage
from ui.dashboard.sidebar import DashboardSidebar
from ui.dashboard.connection_test_controller import ConnectionTestController
from ui.dashboard.dialogs import DashboardDialog
from ui.dashboard.input_controls import finish_input, scroll_page_with_wheel


class DashboardWindow(QMainWindow):
    DEFAULT_WIDTH = 900
    DEFAULT_HEIGHT = 760
    MINIMUM_WIDTH = 650
    MINIMUM_HEIGHT = 600
    AUTO_COLLAPSE_WIDTH = 800

    def __init__(
        self,
        parent=None,
        page_definitions: tuple[PageDefinition, ...] | None = None,
        settings_backend=None,
        group_backend=None,
    ):
        super().__init__(parent)
        self.setObjectName("dashboardWindow")
        self.setWindowTitle("Nova 設定")
        self._wheel_filter_installed = False
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        self.page_definitions = page_definitions or default_page_definitions()
        self.settings_backend = settings_service if settings_backend is None else settings_backend
        self._original_snapshot = self.settings_backend.load()
        self._draft_snapshot = self._original_snapshot
        self.group_backend = (APIGroupService(self.settings_backend.store)
                              if group_backend is None and settings_backend is None else group_backend)
        self._group_load_error = None
        self._original_groups = self._read_groups()
        self._draft_groups = self._original_groups
        self._allow_close = False
        self._page_indexes = {
            definition.key: index
            for index, definition in enumerate(self.page_definitions)
        }
        self._manual_collapsed = False
        self._was_narrow = self.width() < self.AUTO_COLLAPSE_WIDTH

        central = QWidget()
        central.setObjectName("dashboardCentralWidget")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = DashboardSidebar(self.page_definitions)
        self.sidebar.page_selected.connect(self.select_page)
        self.sidebar.collapsed_changed.connect(self._remember_sidebar_choice)
        layout.addWidget(self.sidebar)

        content_container = QWidget()
        content_container.setObjectName("dashboardContentContainer")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("dashboardContentStack")
        self.general_page: GeneralPage | None = None
        self.appearance_page: AppearancePage | None = None
        self.behavior_page: BehaviorPage | None = None
        self.ai_page: AIPage | None = None
        self.personality_page: PersonalityPage | None = None
        for definition in self.page_definitions:
            page = definition.factory()
            page.setObjectName(f"dashboardPage_{definition.key}")
            self.content_stack.addWidget(page)
            if definition.key == "general" and isinstance(page, GeneralPage):
                self.general_page = page
                page.load_snapshot(self._draft_snapshot)
                page.settings_changed.connect(self._update_always_on_top)
                page.clear_history_requested.connect(self._confirm_clear_history)
            elif definition.key == "appearance" and isinstance(page, AppearancePage):
                self.appearance_page = page
                page.load_snapshot(self._draft_snapshot)
                page.size_changed.connect(self._update_pet_size)
            elif definition.key == "behavior" and isinstance(page, BehaviorPage):
                self.behavior_page = page
                page.load_snapshot(self._draft_snapshot)
                page.reading_idle_changed.connect(self._update_reading_idle)
            elif definition.key == "ai" and isinstance(page, AIPage):
                self.ai_page = page
                page.load_snapshot(self._draft_snapshot)
                page.settings_changed.connect(self._update_ai_settings)
                page.group_editor.settings_changed.connect(self._update_groups)
            elif definition.key == "personality" and isinstance(page, PersonalityPage):
                self.personality_page = page
                page.load_snapshot(self._draft_snapshot)
                page.settings_changed.connect(self._update_personality)
        content_layout.addWidget(self.content_stack, 1)
        self.connection_tests = ConnectionTestController(self)
        if self.ai_page is not None:
            self.ai_page.test_requested.connect(self.connection_tests.start)
            self.ai_page.group_editor.test_requested.connect(self.connection_tests.start_group)
            self._load_group_editor()

        action_bar = QWidget()
        action_bar.setObjectName("dashboardActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(24, 12, 24, 12)
        action_layout.setSpacing(10)

        self.change_status_label = QLabel("沒有未儲存的變更")
        self.change_status_label.setObjectName("dashboardChangeStatus")
        action_layout.addWidget(self.change_status_label, 1)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("dashboardCancelButton")
        self.cancel_button.clicked.connect(self.cancel_changes)
        action_layout.addWidget(self.cancel_button)

        self.apply_button = QPushButton("套用")
        self.apply_button.setObjectName("dashboardApplyButton")
        self.apply_button.clicked.connect(self.apply_changes)
        action_layout.addWidget(self.apply_button)
        content_layout.addWidget(action_bar)

        layout.addWidget(content_container, 1)
        self.setCentralWidget(central)

        if self.page_definitions:
            self.select_page(self.page_definitions[0].key)
        self._update_dirty_state()
        self._apply_styles()

    @property
    def current_page_key(self) -> str | None:
        index = self.content_stack.currentIndex()
        if index < 0:
            return None
        return self.page_definitions[index].key

    def select_page(self, key: str) -> None:
        if key not in self._page_indexes:
            raise KeyError(f"Unknown dashboard page: {key}")
        self.content_stack.setCurrentIndex(self._page_indexes[key])
        self.sidebar.set_selected(key)

    def _remember_sidebar_choice(self, collapsed: bool) -> None:
        self._manual_collapsed = collapsed

    @property
    def is_dirty(self) -> bool:
        return (self._draft_snapshot != self._original_snapshot
                or self._draft_groups != self._original_groups)

    def _read_groups(self):
        self._group_load_error = None
        if self.group_backend is None:
            return APIGroupSettings()
        try:
            existing = self.group_backend.load()
            if existing is not None:
                return existing
            # Preview migration in memory only; cancellation must not create files.
            return migrate_legacy_api(self.group_backend.store.get_legacy_api_values(),
                                      bool(os.environ.get("OPENAI_API_KEY", "").strip()))
        except SettingsValidationError as error:
            self._group_load_error = str(error)
            return APIGroupSettings()

    def _load_group_editor(self):
        if self.ai_page is None:
            return
        page = self.ai_page
        page.set_group_mode(self.group_backend is not None)
        page.group_editor.setVisible(self.group_backend is not None)
        page.group_editor.setEnabled(self._group_load_error is None)
        page.group_error_label.setVisible(self._group_load_error is not None)
        page.group_error_label.setText(self._group_load_error or "")
        page.group_editor.load_settings(self._draft_groups)

    def _update_groups(self, settings):
        self._draft_groups = settings
        self._update_dirty_state()

    def _update_always_on_top(self, enabled: bool) -> None:
        self._draft_snapshot = replace(self._draft_snapshot, always_on_top=enabled)
        self._update_dirty_state()

    def _update_dirty_state(self) -> None:
        dirty = self.is_dirty
        self.apply_button.setEnabled(dirty)
        self.change_status_label.setText("有未儲存的變更" if dirty else "沒有未儲存的變更")

    def _update_pet_size(self, width: int, height: int) -> None:
        self._draft_snapshot = replace(self._draft_snapshot, width=width, height=height)
        self._update_dirty_state()

    def _load_pages(self, snapshot) -> None:
        for page in (self.general_page, self.appearance_page, self.behavior_page,
                     self.ai_page, self.personality_page):
            if page is not None:
                page.load_snapshot(snapshot)

    def _update_reading_idle(self, seconds: int) -> None:
        self._draft_snapshot = replace(self._draft_snapshot, reading_idle_seconds=seconds)
        self._update_dirty_state()

    def apply_changes(self) -> bool:
        for page in (self.appearance_page, self.behavior_page, self.ai_page):
            if page is not None:
                page.commit_pending_input()
        if self.ai_page is not None and self.group_backend is not None:
            self.ai_page.group_editor.commit_pending_input()
        group_changed = self._draft_groups != self._original_groups
        try:
            if self.ai_page is not None and self.group_backend is not None:
                self.ai_page.group_editor.validate_draft()
            if group_changed:
                validate_api_groups(self._draft_groups)
                saved = self.settings_backend.save(self._draft_snapshot, api_groups=self._draft_groups,
                                                   group_settings_mode=True)
            else:
                options = {"group_settings_mode": True} if self.group_backend is not None else {}
                saved = self.settings_backend.save(self._draft_snapshot, **options)
        except SettingsValidationError as exc:
            DashboardDialog.warning(self, "設定內容無效", str(exc))
            return False
        except Exception:
            logger.error("Failed to save dashboard settings", exc_info=True)
            DashboardDialog.warning(self, "儲存失敗", "設定未完整儲存，請稍後再試。")
            return False

        self._original_snapshot = saved
        self._draft_snapshot = saved
        self._original_groups = self._draft_groups
        self._load_pages(saved)
        self._load_group_editor()
        self._update_dirty_state()
        self.change_status_label.setText("設定已儲存")
        return True

    def _update_ai_settings(self, values: dict) -> None:
        self._draft_snapshot = replace(self._draft_snapshot, **values)
        self._update_dirty_state()

    def _update_personality(self, selected: str, custom: str) -> None:
        self._draft_snapshot = replace(self._draft_snapshot,
                                       selected_personality=selected, custom_personality=custom)
        self._update_dirty_state()

    def cancel_changes(self) -> None:
        self._restore_original()
        self._allow_close = True
        self.close()

    def load_settings(self) -> None:
        """Reload on reopening, never on recalling a visible draft."""
        snapshot = self.settings_backend.load()
        groups = self._read_groups()
        self.connection_tests.invalidate()
        self._original_snapshot = snapshot
        self._draft_snapshot = snapshot
        self._original_groups = groups
        self._draft_groups = groups
        self._load_pages(snapshot)
        self._load_group_editor()
        self._allow_close = False
        self._update_dirty_state()

    def _restore_original(self) -> None:
        self._draft_snapshot = self._original_snapshot
        self._draft_groups = self._original_groups
        self._load_pages(self._original_snapshot)
        self._load_group_editor()
        self._update_dirty_state()

    def _confirm_clear_history(self) -> None:
        result = DashboardDialog.question(
            self,
            "確認刪除對話紀錄",
            "確定要刪除所有對話紀錄嗎？這個動作無法復原。",
            DashboardDialog.StandardButton.Yes | DashboardDialog.StandardButton.No,
            DashboardDialog.StandardButton.No,
        )
        if result != DashboardDialog.StandardButton.Yes:
            return

        try:
            self.settings_backend.clear_history()
        except Exception:
            logger.error("Failed to clear conversation history", exc_info=True)
            DashboardDialog.warning(self, "刪除失敗", "無法刪除對話紀錄，請稍後再試。")
            return
        DashboardDialog.information(self, "已刪除", "對話紀錄已清空。")

    def closeEvent(self, event) -> None:
        if self._allow_close or not self.is_dirty:
            self.connection_tests.invalidate()
            event.accept()
            return

        result = DashboardDialog.question(
            self,
            "尚有未儲存的變更",
            "要在關閉前儲存變更嗎？",
            DashboardDialog.StandardButton.Save
            | DashboardDialog.StandardButton.Discard
            | DashboardDialog.StandardButton.Cancel,
            DashboardDialog.StandardButton.Save,
        )
        if result == DashboardDialog.StandardButton.Save:
            if self.apply_changes():
                self.connection_tests.invalidate()
                event.accept()
            else:
                event.ignore()
        elif result == DashboardDialog.StandardButton.Discard:
            self._restore_original()
            self.connection_tests.invalidate()
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event) -> None:
        self._allow_close = False
        if not self._wheel_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._wheel_filter_installed = True
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if self._wheel_filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._wheel_filter_installed = False
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        is_narrow = event.size().width() < self.AUTO_COLLAPSE_WIDTH
        if is_narrow != self._was_narrow:
            self._was_narrow = is_narrow
            self.sidebar.set_collapsed(
                True if is_narrow else self._manual_collapsed,
                emit_signal=False,
            )

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

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, #dashboardCentralWidget, #dashboardContentContainer,
            #dashboardContentStack,
            #dashboardPageContent {
                background-color: #ffffff;
                color: #24212a;
            }
            #dashboardSidebar {
                background-color: #f6f5f8;
                border-right: 1px solid #dedbe3;
            }
            #dashboardSidebarTitle {
                color: #24212a;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton#dashboardSidebarToggle {
                background-color: transparent;
                border: 1px solid #cbc7d0;
                border-radius: 7px;
                color: #514b59;
                font-size: 20px;
            }
            QPushButton#dashboardSidebarToggle:hover,
            QPushButton#dashboardSidebarToggle:focus {
                background-color: #ece8f2;
                border-color: #7b4ba0;
                color: #5f2d82;
            }
            #dashboardSidebar QPushButton[checkable="true"] {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: #514b59;
                padding: 8px 10px;
                text-align: left;
            }
            #dashboardSidebar QPushButton[checkable="true"]:hover,
            #dashboardSidebar QPushButton[checkable="true"]:focus {
                background-color: #ece8f2;
                border-color: #d4c7df;
            }
            #dashboardSidebar QPushButton[checkable="true"]:checked {
                background-color: #eadcf5;
                border-color: #9b69bd;
                color: #51276d;
                font-weight: 600;
            }
            #dashboardPageHeading {
                color: #24212a;
                font-size: 26px;
                font-weight: 650;
            }
            #dashboardPageDescription {
                color: #625d68;
                font-size: 14px;
            }
            #dashboardPlaceholderStatus {
                background-color: #f7f5f9;
                border: 1px solid #ded8e4;
                border-radius: 10px;
                color: #6d6673;
                padding: 18px;
            }
            #dashboardSettingsCard {
                background-color: #faf9fb;
                border: 1px solid #e2dfe6;
                border-radius: 10px;
            }
            #dashboardApiGroupList {
                background-color: #f7f5f9;
                border: 1px solid #ded8e4;
                border-radius: 10px;
            }
            QPushButton#dashboardApiGroupButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: #514b59;
                padding: 8px 10px;
                text-align: left;
            }
            QPushButton#dashboardApiGroupButton:hover,
            QPushButton#dashboardApiGroupButton:focus {
                background-color: #efebf3;
                border-color: #d8cfdf;
            }
            QPushButton#dashboardApiGroupButton:checked {
                background-color: #eadcf5;
                border-color: #9b69bd;
                color: #51276d;
                font-weight: 600;
            }
            #dashboardApiKeyRow {
                background-color: #ffffff;
                border: 1px solid #ded8e4;
                border-radius: 9px;
            }
            #dashboardStatusBadge {
                background-color: #eadcf5;
                border: 1px solid #d4bce7;
                border-radius: 10px;
                color: #5f2d82;
                font-size: 12px;
                font-weight: 600;
                padding: 3px 8px;
            }
            #dashboardSummaryPrimary {
                color: #3f3944;
                font-size: 14px;
                font-weight: 500;
            }
            QLabel[validationError="true"] {
                color: #b3261e;
                font-weight: 600;
            }
            #dashboardSectionTitle {
                color: #2e2932;
                font-size: 16px;
                font-weight: 600;
            }
            #dashboardSettingsCard QLabel, #dashboardSettingsCard QCheckBox,
            #dashboardSettingsCard QRadioButton {
                color: #3f3944;
                spacing: 8px;
            }
            #dashboardSettingsCard QSpinBox, #dashboardSettingsCard QDoubleSpinBox,
            #dashboardSettingsCard QLineEdit, #dashboardSettingsCard QComboBox {
                background-color: #ffffff;
                color: #3f3944;
                border: 1px solid #cfcad4;
                border-radius: 6px;
                min-height: 32px;
                padding-left: 8px;
            }
            #dashboardSettingsCard QSpinBox:focus,
            #dashboardSettingsCard QDoubleSpinBox:focus,
            #dashboardSettingsCard QLineEdit:focus,
            #dashboardSettingsCard QComboBox:focus {
                border: 2px solid #7b4ba0;
            }
            #dashboardSettingsCard QPushButton:focus {
                border: 2px solid #7b4ba0;
            }
            QPushButton#dashboardNumberStepButton {
                background-color: #ffffff;
                border: 1px solid #cfcad4;
                border-radius: 6px;
                color: #514b59;
                font-size: 18px;
                padding: 0;
            }
            #dashboardSettingsCard QPlainTextEdit {
                background-color: #ffffff;
                color: #3f3944;
                border: 1px solid #cfcad4;
                border-radius: 6px;
                padding: 8px;
            }
            #dashboardSettingsCard QPlainTextEdit:disabled {
                background-color: #f0edf3;
                color: #827a89;
            }
            QPushButton#dashboardNumberStepButton:hover {
                background-color: #ece8f2;
                border-color: #7b4ba0;
            }
            QPushButton#dashboardNumberStepButton:disabled {
                color: #aaa4b0;
                background-color: #f4f2f6;
            }
            #dashboardActionBar {
                background-color: #f8f7f9;
                border-top: 1px solid #dedbe3;
            }
            #dashboardChangeStatus {
                color: #716a77;
            }
            #dashboardActionBar QPushButton {
                min-width: 78px;
                min-height: 34px;
                border-radius: 7px;
                padding: 0 12px;
            }
            #dashboardCancelButton {
                background-color: #ffffff;
                border: 1px solid #cfcad4;
                color: #49424e;
            }
            #dashboardApplyButton {
                background-color: #704294;
                border: 1px solid #704294;
                color: #ffffff;
            }
            #dashboardApplyButton:disabled {
                background-color: #d7d2db;
                border-color: #d7d2db;
                color: #8e8793;
            }
            #dashboardDangerButton {
                background-color: #ffffff;
                border: 1px solid #b3261e;
                border-radius: 7px;
                color: #b3261e;
                min-height: 34px;
                padding: 0 12px;
            }
            #dashboardDangerButton:hover,
            #dashboardDangerButton:focus {
                background-color: #fff1f0;
            }
            """
        )
