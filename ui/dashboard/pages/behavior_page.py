from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from app.settings import SettingsSnapshot
from ui.dashboard.number_input import IntegerInput
from ui.dashboard.input_controls import FocusClearingWidget


class BehaviorPage(QScrollArea):
    reading_idle_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        content = FocusClearingWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        heading = QLabel("行為")
        heading.setObjectName("dashboardPageHeading")
        layout.addWidget(heading)
        description = QLabel("管理桌寵待機時進入閱讀狀態的等待時間。")
        description.setObjectName("dashboardPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        card = QWidget()
        card.setObjectName("dashboardSettingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel("閱讀待機")
        title.setObjectName("dashboardSectionTitle")
        card_layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.reading_idle_seconds_input = IntegerInput()
        self.reading_idle_seconds_input.setRange(10, 3600)
        self.reading_idle_seconds_input.setSingleStep(10)
        self.reading_idle_seconds_input.setSuffix(" 秒")
        self.reading_idle_seconds_input.setAccessibleName("進入閱讀狀態的閒置秒數")
        form.addRow("進入閱讀狀態的閒置時間：", self.reading_idle_seconds_input)
        card_layout.addLayout(form)

        hint = QLabel("可設定 10–3600 秒。按下套用才會儲存；不會改變閱讀動畫本身。")
        hint.setObjectName("dashboardPageDescription")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        self.setWidget(content)
        self.reading_idle_seconds_input.valueChanged.connect(self.reading_idle_changed)

    def commit_pending_input(self) -> None:
        self.reading_idle_seconds_input.interpretText()

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        with QSignalBlocker(self.reading_idle_seconds_input):
            self.reading_idle_seconds_input.setValue(snapshot.reading_idle_seconds)
