from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.settings import SettingsSnapshot


class AppearancePage(QScrollArea):
    size_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        heading = QLabel("外觀")
        heading.setObjectName("dashboardPageHeading")
        layout.addWidget(heading)
        description = QLabel("調整桌寵尺寸。按下套用後才會儲存並更新桌寵。")
        description.setObjectName("dashboardPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        card = QWidget()
        card.setObjectName("dashboardSettingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel("桌寵尺寸")
        title.setObjectName("dashboardSectionTitle")
        card_layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(14)
        self.width_input = self._size_input("桌寵寬度")
        self.height_input = self._size_input("桌寵高度")
        form.addRow("寬度：", self.width_input)
        form.addRow("高度：", self.height_input)
        card_layout.addLayout(form)
        hint = QLabel("可設定 100–1000 px；此處調整的是桌寵，不是設定視窗。")
        hint.setObjectName("dashboardPageDescription")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        self.setWidget(content)
        self.width_input.valueChanged.connect(self._emit_size)
        self.height_input.valueChanged.connect(self._emit_size)

    @staticmethod
    def _size_input(name: str) -> QSpinBox:
        control = QSpinBox()
        control.setRange(100, 1000)
        control.setSingleStep(10)
        control.setSuffix(" px")
        control.setAccessibleName(name)
        return control

    def _emit_size(self, _value: int) -> None:
        self.size_changed.emit(self.width_input.value(), self.height_input.value())

    def commit_pending_input(self) -> None:
        self.width_input.interpretText()
        self.height_input.interpretText()

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        with QSignalBlocker(self.width_input), QSignalBlocker(self.height_input):
            self.width_input.setValue(snapshot.width)
            self.height_input.setValue(snapshot.height)
