from contextlib import ExitStack

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QLabel, QLineEdit,
    QScrollArea, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
)

from app.contracts.settings import LegacyKeyInput, SettingsDisplay
from app.contracts.settings import ConnectionInputs
from ui.settings.widgets.number_input import DecimalInput, IntegerInput
from ui.settings.widgets.api_group_editor import APIGroupEditor
from ui.settings.widgets.input_controls import FocusClearingWidget, NoWheelCheckBox


class AIPage(QScrollArea):
    settings_changed = Signal(dict)
    test_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._group_mode = False
        self._legacy_cards = []
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        content = FocusClearingWidget()
        content.setObjectName("settingsPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        heading = QLabel("AI")
        heading.setObjectName("settingsPageHeading")
        layout.addWidget(heading)
        description = QLabel("管理模型與對話記憶。修改後按下套用才會儲存。")
        description.setObjectName("settingsPageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.group_error_label = QLabel()
        self.group_error_label.setWordWrap(True)
        self.group_error_label.setObjectName("settingsPageDescription")
        self.group_error_label.hide()
        layout.addWidget(self.group_error_label)
        self.group_editor = APIGroupEditor()
        layout.addWidget(self.group_editor)
        legacy_notice = QLabel("目前正式聊天及下方連線測試仍使用這份舊設定。上方群組設定尚未接入正式呼叫。")
        legacy_notice.setWordWrap(True)
        legacy_notice.setObjectName("settingsPageDescription")
        layout.addWidget(legacy_notice)
        self._legacy_notice = legacy_notice

        self.api_key_rows = []
        self._next_row_id = 0
        self._loading = False
        key_form = self._card(layout, "API Keys")
        self._legacy_cards.append(key_form.parentWidget())
        self.api_keys_container = QWidget()
        self.api_keys_layout = QVBoxLayout(self.api_keys_container)
        self.api_keys_layout.setContentsMargins(0, 0, 0, 0)
        key_form.addRow(self.api_keys_container)
        self.add_api_key_button = QPushButton("新增 API Key")
        self.add_api_key_button.clicked.connect(lambda: self.add_api_key_row())
        key_form.addRow(self.add_api_key_button)
        key_note = QLabel("金鑰以遮蔽方式顯示。測試使用目前輸入，不會自動儲存，且可能消耗服務額度。")
        key_note.setObjectName("settingsPageDescription")
        key_note.setWordWrap(True)
        key_form.addRow(key_note)

        model_form = self._card(layout, "模型設定")
        self._legacy_cards.append(model_form.parentWidget())
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("模型名稱")
        self.temperature_input = DecimalInput()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setDecimals(1)
        self.temperature_input.setSingleStep(0.1)
        model_form.addRow("Base URL：", self.base_url_input)
        model_form.addRow("模型：", self.model_input)
        model_form.addRow("溫度：", self.temperature_input)

        memory_form = self._card(layout, "對話記憶")
        self.max_memory_turns_input = IntegerInput()
        self.max_memory_turns_input.setRange(0, 50)
        self.history_limit_input = IntegerInput()
        self.history_limit_input.setRange(1, 100)
        self.conversation_summary_check = NoWheelCheckBox("啟用過去對話摘要")
        memory_form.addRow("最大記憶輪數：", self.max_memory_turns_input)
        memory_form.addRow("歷史紀錄上限：", self.history_limit_input)
        memory_form.addRow(self.conversation_summary_check)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.group_editor.set_available_width(max(0, self.viewport().width() - 64))

    def connection_inputs(self) -> ConnectionInputs:
        group_inputs = self.group_editor.connection_inputs()
        return ConnectionInputs(
            self.collect_connection_keys(), group_inputs.generation, group_inputs.targets,
        )

    def collect_connection_keys(self) -> dict[int, str]:
        """Return a detached snapshot; callers never need the widget rows."""
        return {row["id"]: row["key_input"].text() for row in self.api_key_rows}

    @staticmethod
    def _card(layout, title):
        card = QWidget()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        heading = QLabel(title)
        heading.setObjectName("settingsSectionTitle")
        card_layout.addWidget(heading)
        form = QFormLayout()
        form.setSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        card_layout.addLayout(form)
        layout.addWidget(card)
        return form

    def _emit_settings(self, _value) -> None:
        if self._loading:
            return
        values = {
            "api_keys": self.collect_api_key_entries(),
            "base_url": self.base_url_input.text(),
            "model": self.model_input.text(),
            "temperature": self.temperature_input.value(),
            "max_memory_turns": self.max_memory_turns_input.value(),
            "history_limit": self.history_limit_input.value(),
            "conversation_summary_enabled": self.conversation_summary_check.isChecked(),
        }
        self.settings_changed.emit(values)

    def set_group_mode(self, enabled):
        self._group_mode = enabled
        self._legacy_notice.setVisible(not enabled)
        for card in self._legacy_cards:
            card.setVisible(not enabled)

    def commit_pending_input(self) -> None:
        for control in (self.temperature_input, self.max_memory_turns_input,
                        self.history_limit_input):
            control.interpretText()

    def load_snapshot(self, snapshot: SettingsDisplay) -> None:
        self._loading = True
        try:
            for row in list(self.api_key_rows):
                self.remove_api_key_row(row["id"], ensure_one=False)
            for entry in snapshot.api_keys:
                self.add_api_key_row(entry.name, entry.key)
            if not self.api_key_rows:
                self.add_api_key_row()
        finally:
            self._loading = False
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

    def add_api_key_row(self, name="", key=""):
        self._next_row_id += 1
        row_id = self._next_row_id
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        fields = QHBoxLayout()
        name_input = QLineEdit(name)
        name_input.setPlaceholderText("名稱")
        name_input.setMaximumWidth(110)
        name_input.setAccessibleName("API Key 名稱")
        key_input = QLineEdit(key)
        key_input.setEchoMode(QLineEdit.Password)
        key_input.setPlaceholderText("API Key")
        key_input.setAccessibleName("API Key")
        test_button = QPushButton("測試")
        remove_button = QPushButton("刪除")
        remove_button.setObjectName("settingsDangerButton")
        for widget in (name_input, key_input, test_button, remove_button):
            fields.addWidget(widget)
        layout.addLayout(fields)
        status = QLabel("")
        status.setObjectName("settingsPageDescription")
        status.setWordWrap(True)
        status.hide()
        layout.addWidget(status)
        row = {"id": row_id, "container": container, "name_input": name_input,
               "key_input": key_input, "test_button": test_button,
               "remove_button": remove_button, "status": status}
        self.api_key_rows.append(row)
        self.api_keys_layout.addWidget(container)
        name_input.textChanged.connect(self._emit_settings)
        key_input.textChanged.connect(self._emit_settings)
        test_button.clicked.connect(lambda: self.test_requested.emit(row_id))
        remove_button.clicked.connect(lambda: self.remove_api_key_row(row_id))
        self._emit_settings(None)
        return row

    def row_for_id(self, row_id):
        return next((row for row in self.api_key_rows if row["id"] == row_id), None)

    def remove_api_key_row(self, row_id, ensure_one=True):
        row = self.row_for_id(row_id)
        if row is None:
            return
        self.api_key_rows.remove(row)
        self.api_keys_layout.removeWidget(row["container"])
        row["container"].hide()
        row["container"].deleteLater()
        if ensure_one and not self.api_key_rows:
            self.add_api_key_row()
        else:
            self._emit_settings(None)

    def collect_api_key_entries(self):
        return tuple(LegacyKeyInput(row["name_input"].text(), row["key_input"].text())
                     for row in self.api_key_rows)

    def begin_test(self, row_id):
        row = self.row_for_id(row_id)
        if row is not None:
            row["test_button"].setEnabled(False)
            row["test_button"].setText("測試中")
            row["status"].setText("正在背景測試連線…")
            row["status"].show()

    def finish_test(self, row_id, message):
        row = self.row_for_id(row_id)
        if row is not None:
            row["test_button"].setEnabled(True)
            row["test_button"].setText("測試")
            row["status"].setText(message)
            row["status"].show()
