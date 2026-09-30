from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from ui.settings.widgets.input_controls import FocusClearingWidget, ToggleSwitch

from app.settings.model import SettingsSnapshot


class GeneralPage(QScrollArea):
    settings_changed = Signal(bool)
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        content = FocusClearingWidget()
        content.setObjectName("settingsPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        heading = QLabel("一般")
        heading.setObjectName("settingsPageHeading")
        heading.setAccessibleName("一般頁面標題")
        layout.addWidget(heading)

        description = QLabel("管理桌寵視窗與本機對話紀錄。")
        description.setObjectName("settingsPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        window_section = QWidget()
        window_section.setObjectName("settingsCard")
        window_layout = QVBoxLayout(window_section)
        window_layout.setContentsMargins(20, 18, 20, 18)
        window_layout.setSpacing(12)

        window_title = QLabel("視窗")
        window_title.setObjectName("settingsSectionTitle")
        window_layout.addWidget(window_title)

        always_on_top_row = QHBoxLayout()
        always_on_top_row.setContentsMargins(0, 0, 0, 0)
        always_on_top_row.setSpacing(12)
        always_on_top_text = QVBoxLayout()
        always_on_top_text.setContentsMargins(0, 0, 0, 0)
        always_on_top_text.setSpacing(3)
        always_on_top_label = QLabel("視窗永遠置頂")
        always_on_top_label.setObjectName("settingsSettingLabel")
        always_on_top_description = QLabel("讓桌寵保持在其他視窗上方；套用後立即更新。")
        always_on_top_description.setObjectName("settingsSettingDescription")
        always_on_top_description.setWordWrap(True)
        always_on_top_text.addWidget(always_on_top_label)
        always_on_top_text.addWidget(always_on_top_description)
        always_on_top_row.addLayout(always_on_top_text, 1)

        self.always_on_top_check = ToggleSwitch()
        self.always_on_top_check.setAccessibleName("視窗永遠置頂")
        self.always_on_top_check.setToolTip("讓桌寵保持在其他視窗上方")
        always_on_top_row.addWidget(self.always_on_top_check, 0, Qt.AlignVCenter)
        self.always_on_top_status = QLabel()
        self.always_on_top_status.setObjectName("settingsToggleStatus")
        self.always_on_top_status.setMinimumWidth(44)
        always_on_top_row.addWidget(self.always_on_top_status, 0, Qt.AlignVCenter)
        self.always_on_top_check.toggled.connect(self._on_always_on_top_changed)
        window_layout.addLayout(always_on_top_row)
        layout.addWidget(window_section)

        history_section = QWidget()
        history_section.setObjectName("settingsDangerCard")
        history_layout = QVBoxLayout(history_section)
        history_layout.setContentsMargins(20, 18, 20, 18)
        history_layout.setSpacing(12)

        history_title = QLabel("對話紀錄")
        history_title.setObjectName("settingsDangerTitle")
        history_layout.addWidget(history_title)

        history_description = QLabel("清除儲存在本機的所有對話紀錄。此操作無法復原。")
        history_description.setObjectName("settingsDangerDescription")
        history_description.setWordWrap(True)
        history_layout.addWidget(history_description)

        self.clear_history_button = QPushButton("刪除對話紀錄")
        self.clear_history_button.setObjectName("settingsDangerButton")
        self.clear_history_button.setAccessibleName("刪除所有對話紀錄")
        self.clear_history_button.clicked.connect(self.clear_history_requested)
        history_layout.addWidget(self.clear_history_button, 0, Qt.AlignRight)
        layout.addWidget(history_section)

        layout.addStretch(1)
        self.setWidget(content)

    def _on_always_on_top_changed(self, enabled: bool) -> None:
        self._update_always_on_top_status(enabled)
        self.settings_changed.emit(enabled)

    def _update_always_on_top_status(self, enabled: bool) -> None:
        self.always_on_top_status.setText("已啟用" if enabled else "已停用")
        self.always_on_top_status.setProperty("active", enabled)
        self.always_on_top_status.style().unpolish(self.always_on_top_status)
        self.always_on_top_status.style().polish(self.always_on_top_status)

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        with QSignalBlocker(self.always_on_top_check):
            self.always_on_top_check.setChecked(snapshot.always_on_top)
        self._update_always_on_top_status(snapshot.always_on_top)
