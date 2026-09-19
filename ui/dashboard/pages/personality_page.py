from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup, QLabel, QPlainTextEdit, QRadioButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.ai.prompt_builder import get_personality_option_labels
from app.settings import SettingsSnapshot
from ui.dashboard.input_controls import FocusClearingWidget


class PersonalityPage(QScrollArea):
    settings_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._loading = False
        self._selected_key = ""
        content = FocusClearingWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        heading = QLabel("人格")
        heading.setObjectName("dashboardPageHeading")
        layout.addWidget(heading)
        description = QLabel("一次選擇一種人格，按下套用才會儲存。")
        description.setObjectName("dashboardPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        card = QWidget()
        card.setObjectName("dashboardSettingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        title = QLabel("人格設定")
        title.setObjectName("dashboardSectionTitle")
        card_layout.addWidget(title)
        self.personality_group = QButtonGroup(self)
        self.personality_buttons = {}
        options = {**get_personality_option_labels(), "custom": "使用自訂人格 Prompt"}
        for key, label in options.items():
            button = QRadioButton(label)
            button.setAccessibleName(label)
            self.personality_buttons[key] = button
            self.personality_group.addButton(button)
            button.toggled.connect(lambda checked, option=key: self._select(option, checked))
            card_layout.addWidget(button)

        self.custom_personality_input = QPlainTextEdit()
        self.custom_personality_input.setAccessibleName("自訂人格內容")
        self.custom_personality_input.setPlaceholderText("輸入完整人格設定，例如：你是 Nova，一位……")
        self.custom_personality_input.setMinimumHeight(150)
        self.custom_personality_input.setEnabled(False)
        self.custom_personality_input.textChanged.connect(self._emit_settings)
        card_layout.addWidget(self.custom_personality_input)
        hint = QLabel("切換回內建人格不會刪除自訂內容；未選擇自訂時，該內容不會用於回覆。")
        hint.setObjectName("dashboardPageDescription")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        self.setWidget(content)

    def _select(self, key, checked):
        if self._loading or not checked:
            return
        self._selected_key = key
        self.custom_personality_input.setEnabled(key == "custom")
        self._emit_settings()

    def _emit_settings(self):
        if not self._loading:
            self.settings_changed.emit(self._selected_key, self.custom_personality_input.toPlainText())

    def load_snapshot(self, snapshot: SettingsSnapshot) -> None:
        self._loading = True
        try:
            self._selected_key = snapshot.selected_personality
            self.personality_group.setExclusive(False)
            for key, button in self.personality_buttons.items():
                button.setChecked(key == snapshot.selected_personality)
            self.custom_personality_input.setPlainText(snapshot.custom_personality)
            self.custom_personality_input.setEnabled(snapshot.selected_personality == "custom")
        finally:
            self.personality_group.setExclusive(True)
            self._loading = False
