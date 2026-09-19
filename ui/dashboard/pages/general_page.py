from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from ui.dashboard.input_controls import FocusClearingWidget, NoWheelCheckBox

from app.settings import SettingsSnapshot


class GeneralPage(QScrollArea):
    settings_changed = Signal(bool)
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        content = FocusClearingWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        heading = QLabel("一般")
        heading.setObjectName("dashboardPageHeading")
        heading.setAccessibleName("一般頁面標題")
        layout.addWidget(heading)

        description = QLabel("管理桌寵視窗與本機對話紀錄。")
        description.setObjectName("dashboardPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        window_section = QWidget()
        window_section.setObjectName("dashboardSettingsCard")
        window_layout = QVBoxLayout(window_section)
        window_layout.setContentsMargins(20, 18, 20, 18)
        window_layout.setSpacing(10)

        window_title = QLabel("視窗")
        window_title.setObjectName("dashboardSectionTitle")
        window_layout.addWidget(window_title)

        self.always_on_top_check = NoWheelCheckBox("視窗永遠置頂")
        self.always_on_top_check.setToolTip("讓桌寵保持在其他視窗上方")
        self.always_on_top_check.toggled.connect(self.settings_changed)
        window_layout.addWidget(self.always_on_top_check)
        layout.addWidget(window_section)

        history_section = QWidget()
        history_section.setObjectName("dashboardSettingsCard")
        history_layout = QVBoxLayout(history_section)
        history_layout.setContentsMargins(20, 18, 20, 18)
        history_layout.setSpacing(10)

        history_title = QLabel("對話紀錄")
        history_title.setObjectName("dashboardSectionTitle")
        history_layout.addWidget(history_title)

        history_description = QLabel("清除儲存在本機的所有對話紀錄。此操作無法復原。")
        history_description.setObjectName("dashboardPageDescription")
        history_description.setWordWrap(True)
        history_layout.addWidget(history_description)

        self.clear_history_button = QPushButton("刪除對話紀錄")
        self.clear_history_button.setObjectName("dashboardDangerButton")
        self.clear_history_button.setAccessibleName("刪除所有對話紀錄")
        self.clear_history_button.clicked.connect(self.clear_history_requested)
        history_layout.addWidget(self.clear_history_button)
        layout.addWidget(history_section)

        layout.addStretch(1)
        self.setWidget(content)

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        self.always_on_top_check.blockSignals(True)
        self.always_on_top_check.setChecked(snapshot.always_on_top)
        self.always_on_top_check.blockSignals(False)
