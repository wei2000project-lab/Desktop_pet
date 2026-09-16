from contextlib import ExitStack

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.settings import SettingsSnapshot


class AIPage(QScrollArea):
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        heading = QLabel("AI")
        heading.setObjectName("dashboardPageHeading")
        layout.addWidget(heading)
        description = QLabel("管理模型與對話記憶。修改後按下套用才會儲存。")
        description.setObjectName("dashboardPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        model_form = self._card(layout, "模型設定")
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("模型名稱")
        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setDecimals(1)
        self.temperature_input.setSingleStep(0.1)
        model_form.addRow("Base URL：", self.base_url_input)
        model_form.addRow("模型：", self.model_input)
        model_form.addRow("溫度：", self.temperature_input)

        memory_form = self._card(layout, "對話記憶")
        self.max_memory_turns_input = QSpinBox()
        self.max_memory_turns_input.setRange(0, 50)
        self.history_limit_input = QSpinBox()
        self.history_limit_input.setRange(1, 100)
        self.conversation_summary_check = QCheckBox("啟用過去對話摘要")
        memory_form.addRow("最大記憶輪數：", self.max_memory_turns_input)
        memory_form.addRow("歷史紀錄上限：", self.history_limit_input)
        memory_form.addRow(self.conversation_summary_check)

        note = QLabel("API Key 管理與連線測試將於下一階段搬入；本頁套用不會變更既有金鑰。")
        note.setObjectName("dashboardPageDescription")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.setWidget(content)

        self._controls = {
            "base_url": self.base_url_input,
            "model": self.model_input,
            "temperature": self.temperature_input,
            "max_memory_turns": self.max_memory_turns_input,
            "history_limit": self.history_limit_input,
            "conversation_summary_enabled": self.conversation_summary_check,
        }
        for field, control in self._controls.items():
            control.setAccessibleName(field)
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self._emit_settings)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._emit_settings)
            else:
                control.valueChanged.connect(self._emit_settings)

    @staticmethod
    def _card(layout, title):
        card = QWidget()
        card.setObjectName("dashboardSettingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        heading = QLabel(title)
        heading.setObjectName("dashboardSectionTitle")
        card_layout.addWidget(heading)
        form = QFormLayout()
        form.setSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        card_layout.addLayout(form)
        layout.addWidget(card)
        return form

    def _emit_settings(self, _value) -> None:
        self.settings_changed.emit({
            "base_url": self.base_url_input.text(),
            "model": self.model_input.text(),
            "temperature": self.temperature_input.value(),
            "max_memory_turns": self.max_memory_turns_input.value(),
            "history_limit": self.history_limit_input.value(),
            "conversation_summary_enabled": self.conversation_summary_check.isChecked(),
        })

    def commit_pending_input(self) -> None:
        for control in (self.temperature_input, self.max_memory_turns_input,
                        self.history_limit_input):
            control.interpretText()

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        with ExitStack() as stack:
            for field, control in self._controls.items():
                stack.enter_context(QSignalBlocker(control))
                value = getattr(snapshot, field)
                if isinstance(control, QLineEdit):
                    control.setText(value)
                elif isinstance(control, QCheckBox):
                    control.setChecked(value)
                else:
                    control.setValue(value)
