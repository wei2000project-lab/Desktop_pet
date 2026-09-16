from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QCheckBox, QPushButton, QFormLayout, QSlider,
    QPlainTextEdit, QMessageBox, QButtonGroup
)
from app.ai.prompt_builder import get_personality_option_labels
from app.settings import ApiKeyEntry, SettingsSnapshot, SettingsValidationError, settings_service
from app.utils.logger import logger


class ApiConnectionTestSignals(QObject):
    finished = Signal(bool, str)


class ApiConnectionTestWorker(QRunnable):
    def __init__(self, base_url: str, api_key: str, model: str, verify_ssl: bool):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.signals = ApiConnectionTestSignals()

    @Slot()
    def run(self):
        try:
            from app.ai.client import AIClient

            client = AIClient(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                verify_ssl=self.verify_ssl,
                timeout=15.0,
            )
            client.test_connection()
        except Exception as exc:
            self.signals.finished.emit(False, str(exc) or type(exc).__name__)
            return
        self.signals.finished.emit(True, "")

class NumberInputWithButtons(QWidget):
    """Custom widget containing a minus button, a centered QLineEdit, and a plus button."""
    def __init__(self, val_min: int, val_max: int, val_step: int = 10, parent=None):
        super().__init__(parent)
        self.val_min = val_min
        self.val_max = val_max
        self.val_step = val_step
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # Minus Button
        self.minus_btn = QPushButton("－")
        self.minus_btn.setFixedSize(26, 26)
        self.minus_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d38;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                color: #e0e0e0;
                font-weight: bold;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #353545;
                border-color: #bb86fc;
                color: #bb86fc;
            }
            QPushButton:pressed {
                background-color: #1e1e24;
            }
        """)
        self.minus_btn.clicked.connect(self.decrement)
        
        # Text Input
        self.line_edit = QLineEdit()
        self.line_edit.setValidator(QIntValidator(val_min, val_max))
        self.line_edit.setAlignment(Qt.AlignCenter)
        self.line_edit.setFixedWidth(75)
        self.line_edit.setStyleSheet("""
            QLineEdit {
                background-color: rgba(45, 45, 55, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                color: #ffffff;
                padding: 4px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #bb86fc;
                background-color: rgba(50, 50, 65, 220);
            }
        """)
        
        # Plus Button
        self.plus_btn = QPushButton("＋")
        self.plus_btn.setFixedSize(26, 26)
        self.plus_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d38;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                color: #e0e0e0;
                font-weight: bold;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #353545;
                border-color: #bb86fc;
                color: #bb86fc;
            }
            QPushButton:pressed {
                background-color: #1e1e24;
            }
        """)
        self.plus_btn.clicked.connect(self.increment)
        
        layout.addWidget(self.minus_btn)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.plus_btn)
        layout.addStretch()
        
        # Connect editingFinished to automatically clamp typed numbers when focus is lost or enter is pressed
        self.line_edit.editingFinished.connect(self.on_editing_finished)

    def on_editing_finished(self):
        try:
            val = int(self.line_edit.text().strip())
            self.setValue(val)
        except ValueError:
            self.setValue(self.val_min)

    def getValue(self) -> int:
        try:
            val = int(self.line_edit.text().strip())
            return max(self.val_min, min(self.val_max, val))
        except ValueError:
            return self.val_min

    def setValue(self, val: int):
        val = max(self.val_min, min(self.val_max, val))
        self.line_edit.setText(str(val))

    def decrement(self):
        val = self.getValue() - self.val_step
        self.setValue(val)

    def increment(self):
        val = self.getValue() + self.val_step
        self.setValue(val)



class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._settings_snapshot = SettingsSnapshot()
        self._api_test_workers = set()
        self._api_test_session = 0
        self.setWindowTitle("Nova 設定 (Settings)")
        self.resize(380, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # Apply dark mode QSS styling
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                background-color: #252530;
                padding: 12px;
            }
            QTabBar::tab {
                background-color: #1c1c22;
                border: 1px solid rgba(255, 255, 255, 10);
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 6px 12px;
                color: #888888;
            }
            QTabBar::tab:selected {
                background-color: #252530;
                color: #bb86fc;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 20);
                border-bottom: none;
            }
            QLineEdit {
                background-color: rgba(45, 45, 55, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                color: #ffffff;
                padding: 5px 8px;
            }
            QLineEdit:focus {
                border: 1px solid #bb86fc;
                background-color: rgba(50, 50, 65, 220);
            }
            QPlainTextEdit {
                background-color: rgba(45, 45, 55, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                color: #ffffff;
                padding: 5px 8px;
            }
            QPlainTextEdit:focus {
                border: 1px solid #bb86fc;
                background-color: rgba(50, 50, 65, 220);
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: rgba(45, 45, 55, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #bb86fc;
                border: 1px solid #bb86fc;
            }
            QPushButton {
                background-color: #2d2d38;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #353545;
                border-color: #bb86fc;
            }
            QPushButton#save_btn {
                background-color: #6200ee;
                border: none;
                color: white;
            }
            QPushButton#save_btn:hover {
                background-color: #7f39fb;
            }
            QPushButton#save_btn:pressed {
                background-color: #3700b3;
            }
        """)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Tab Widget
        self.tabs = QTabWidget(self)
        
        # --- Tab 1: AI Settings ---
        self.ai_tab = QWidget()
        ai_layout = QFormLayout(self.ai_tab)
        ai_layout.setContentsMargins(5, 5, 5, 5)
        ai_layout.setSpacing(12)

        self.api_key_rows = []
        self.api_keys_container = QWidget()
        self.api_keys_layout = QVBoxLayout(self.api_keys_container)
        self.api_keys_layout.setContentsMargins(0, 0, 0, 0)
        self.api_keys_layout.setSpacing(6)
        self.add_api_key_btn = QPushButton("新增 API Key")
        self.add_api_key_btn.clicked.connect(lambda: self.add_api_key_row())
        
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("例如 https://api.openai.com/v1")
        
        self.model_input = QLineEdit()
        
        # Temperature Slider layout
        temp_layout = QHBoxLayout()
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 20)
        self.temp_slider.setSingleStep(1)
        self.temp_slider.setPageStep(2)
        self.temp_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #2d2d38;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #bb86fc;
                width: 14px;
                height: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
        """)
        
        self.temp_val_label = QLabel("0.7")
        self.temp_val_label.setFixedWidth(25)
        self.temp_val_label.setStyleSheet("color: #bb86fc; font-weight: bold; background: transparent;")
        self.temp_slider.valueChanged.connect(self.on_temp_slider_changed)
        
        temp_layout.addWidget(self.temp_slider)
        temp_layout.addWidget(self.temp_val_label)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.setSpacing(8)
        
        self.max_memory_turns_input = NumberInputWithButtons(0, 50, 1)
        self.history_limit_input = NumberInputWithButtons(1, 100, 1)
        self.conversation_summary_check = QCheckBox("啟用過去對話摘要")
        
        api_keys_label = QLabel("API Keys:")
        api_keys_label.setStyleSheet("color: #bbbbbb; background: transparent; font-weight: bold;")
        ai_layout.addRow(api_keys_label)
        ai_layout.addRow(self.api_keys_container)
        ai_layout.addRow(self.add_api_key_btn)
        ai_layout.addRow(QLabel("Base URL:"), self.base_url_input)
        ai_layout.addRow(QLabel("Model:"), self.model_input)
        ai_layout.addRow(QLabel("Temperature:"), temp_layout)
        ai_layout.addRow(QLabel("最大記憶輪數:"), self.max_memory_turns_input)
        ai_layout.addRow(QLabel("歷史紀錄上限:"), self.history_limit_input)
        ai_layout.addRow(self.conversation_summary_check)

        # --- Tab 2: Personality Settings ---
        self.personality_tab = QWidget()
        personality_layout = QVBoxLayout(self.personality_tab)
        personality_layout.setContentsMargins(5, 5, 5, 5)
        personality_layout.setSpacing(10)

        personality_title = QLabel("一次只能勾選一個，勾選後會套用完整人格 Prompt")
        personality_title.setStyleSheet("color: #bbbbbb; background: transparent;")
        personality_layout.addWidget(personality_title)

        self.personality_checks = {}
        self.personality_group = QButtonGroup(self)
        self.personality_group.setExclusive(True)
        for key, label in get_personality_option_labels().items():
            checkbox = QCheckBox(label)
            self.personality_checks[key] = checkbox
            self.personality_group.addButton(checkbox)
            personality_layout.addWidget(checkbox)

        self.custom_personality_check = QCheckBox("使用自訂人格 Prompt")
        self.personality_group.addButton(self.custom_personality_check)
        personality_layout.addWidget(self.custom_personality_check)

        self.custom_personality_input = QPlainTextEdit()
        self.custom_personality_input.setPlaceholderText("輸入一段完整人格設定，例如：你是 Nova，一位... 回覆時...")
        self.custom_personality_input.setFixedHeight(95)
        self.custom_personality_check.toggled.connect(self.custom_personality_input.setEnabled)
        personality_layout.addWidget(self.custom_personality_input)
        personality_layout.addStretch()

        # --- Tab 3: Pet Settings ---
        self.pet_tab = QWidget()
        pet_layout = QFormLayout(self.pet_tab)
        pet_layout.setContentsMargins(5, 5, 5, 5)
        pet_layout.setSpacing(12)

        # Use custom NumberInputWithButtons for width, height, and reading idle threshold.
        self.width_input = NumberInputWithButtons(100, 1000, 10)
        self.height_input = NumberInputWithButtons(100, 1000, 10)
        self.always_on_top_check = QCheckBox("視窗永遠置頂 (Always on Top)")
        self.reading_idle_seconds_input = NumberInputWithButtons(10, 3600, 10)

        pet_layout.addRow(QLabel("寬度 (Width):"), self.width_input)
        pet_layout.addRow(QLabel("高度 (Height):"), self.height_input)
        pet_layout.addRow(self.always_on_top_check)
        pet_layout.addRow(QLabel("進入閱讀狀態閒置秒數:"), self.reading_idle_seconds_input)

        # Add tabs
        self.tabs.addTab(self.ai_tab, "AI 對話設定")
        self.tabs.addTab(self.personality_tab, "模型人格設定")
        self.tabs.addTab(self.pet_tab, "桌寵外觀設定")
        main_layout.addWidget(self.tabs)

        # --- Bottom Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.clear_history_btn = QPushButton("刪除對話紀錄")
        self.clear_history_btn.clicked.connect(self.confirm_clear_history)

        btn_layout.addWidget(self.clear_history_btn)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.close)
        
        self.save_btn = QPushButton("儲存")
        self.save_btn.setObjectName("save_btn")
        self.save_btn.clicked.connect(self.save_settings)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        main_layout.addLayout(btn_layout)

    def add_api_key_row(self, name: str = "", key: str = ""):
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        name_input = QLineEdit()
        name_input.setPlaceholderText("名稱")
        name_input.setFixedWidth(48)
        name_input.setText(name)

        key_input = QLineEdit()
        key_input.setPlaceholderText("請輸入 API Key...")
        key_input.setEchoMode(QLineEdit.Password)
        key_input.setText(key)

        test_btn = QPushButton("測試")
        test_btn.setFixedWidth(64)
        test_btn.setStyleSheet("""
            QPushButton {
                padding-left: 6px;
                padding-right: 6px;
            }
        """)
        remove_btn = QPushButton("🗑")
        remove_btn.setFixedSize(30, 28)
        remove_btn.setToolTip("刪除 API Key")
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #b3261e;
                border: 1px solid #d93025;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #d93025;
                border-color: #ff6b5f;
            }
            QPushButton:pressed {
                background-color: #7f1d1d;
            }
        """)

        row = {
            "layout": row_layout,
            "name_input": name_input,
            "key_input": key_input,
            "test_btn": test_btn,
            "remove_btn": remove_btn,
        }
        test_btn.clicked.connect(lambda checked=False, item=row: self.test_api_key_row(item))
        remove_btn.clicked.connect(lambda checked=False, item=row: self.remove_api_key_row(item))

        row_layout.addWidget(name_input)
        row_layout.addWidget(key_input)
        row_layout.addWidget(test_btn)
        row_layout.addWidget(remove_btn)
        self.api_keys_layout.addLayout(row_layout)
        self.api_key_rows.append(row)

    def remove_api_key_row(self, row, ensure_one: bool = True):
        if row not in self.api_key_rows:
            return
        self.api_key_rows.remove(row)
        layout = row["layout"]
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.api_keys_layout.removeItem(layout)
        if ensure_one and not self.api_key_rows:
            self.add_api_key_row()

    def collect_api_key_entries(self):
        entries = []
        for row in self.api_key_rows:
            name = row["name_input"].text().strip()
            key = row["key_input"].text().strip()
            if key:
                entries.append(ApiKeyEntry(name or f"Key {len(entries) + 1}", key))
        return tuple(entries)

    def test_api_key_row(self, row):
        key = row["key_input"].text().strip()
        if not key:
            QMessageBox.warning(self, "測試連線", "請先輸入 API Key。")
            return

        test_btn = row["test_btn"]
        if not test_btn.isEnabled():
            return
        test_btn.setEnabled(False)
        test_btn.setText("測試中")

        worker = ApiConnectionTestWorker(
            base_url=self.base_url_input.text().strip() or "https://api.openai.com/v1",
            api_key=key,
            model=self.model_input.text().strip() or "gpt-4o-mini",
            verify_ssl=self._settings_snapshot.verify_ssl,
        )
        session = self._api_test_session
        worker.signals.finished.connect(
            lambda success, message, item=row, task=worker, token=session:
                self.on_api_test_finished(item, task, token, success, message)
        )
        self._api_test_workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def on_api_test_finished(self, row, worker, session, success, message):
        self._api_test_workers.discard(worker)
        if row not in self.api_key_rows:
            return
        row["test_btn"].setEnabled(True)
        row["test_btn"].setText("測試")
        if session != self._api_test_session:
            return
        if success:
            QMessageBox.information(self, "測試連線成功", "此 API Key 可以成功連線。")
        else:
            QMessageBox.warning(self, "測試連線失敗", message)

    def closeEvent(self, event):
        self._api_test_session += 1
        super().closeEvent(event)

    def on_temp_slider_changed(self, value: int):
        self.temp_val_label.setText(f"{value / 10.0:.1f}")

    def load_settings(self):
        snapshot = settings_service.load()
        self._settings_snapshot = snapshot

        for row in list(self.api_key_rows):
            self.remove_api_key_row(row, ensure_one=False)
        for entry in snapshot.api_keys:
            self.add_api_key_row(entry.name, entry.key)
        if not self.api_key_rows:
            self.add_api_key_row()
        self.base_url_input.setText(snapshot.base_url)
        self.model_input.setText(snapshot.model)
        self.temp_slider.setValue(int(snapshot.temperature * 10))
        self.temp_val_label.setText(f"{snapshot.temperature:.1f}")
        self.max_memory_turns_input.setValue(snapshot.max_memory_turns)
        self.history_limit_input.setValue(snapshot.history_limit)
        self.conversation_summary_check.setChecked(snapshot.conversation_summary_enabled)

        for key, checkbox in self.personality_checks.items():
            checkbox.setChecked(key == snapshot.selected_personality)
        self.custom_personality_check.setChecked(snapshot.selected_personality == "custom")
        self.custom_personality_input.setPlainText(snapshot.custom_personality)
        self.custom_personality_input.setEnabled(self.custom_personality_check.isChecked())

        self.width_input.setValue(snapshot.width)
        self.height_input.setValue(snapshot.height)
        self.always_on_top_check.setChecked(snapshot.always_on_top)
        self.reading_idle_seconds_input.setValue(snapshot.reading_idle_seconds)

    def save_settings(self):
        logger.info("Saving settings window configuration...")
        selected_personality = ""
        for key, checkbox in self.personality_checks.items():
            if checkbox.isChecked():
                selected_personality = key
                break
        if self.custom_personality_check.isChecked():
            selected_personality = "custom"

        snapshot = SettingsSnapshot(
            api_keys=self.collect_api_key_entries(),
            base_url=self.base_url_input.text(),
            model=self.model_input.text(),
            temperature=self.temp_slider.value() / 10.0,
            verify_ssl=self._settings_snapshot.verify_ssl,
            width=self.width_input.getValue(),
            height=self.height_input.getValue(),
            always_on_top=self.always_on_top_check.isChecked(),
            max_memory_turns=self.max_memory_turns_input.getValue(),
            history_limit=self.history_limit_input.getValue(),
            conversation_summary_enabled=self.conversation_summary_check.isChecked(),
            reading_idle_seconds=self.reading_idle_seconds_input.getValue(),
            selected_personality=selected_personality,
            custom_personality=self.custom_personality_input.toPlainText(),
        )
        try:
            self._settings_snapshot = settings_service.save(snapshot)
        except SettingsValidationError as exc:
            QMessageBox.warning(self, "設定內容無效", str(exc))
            return
        except Exception:
            logger.error("Failed to save settings", exc_info=True)
            QMessageBox.warning(self, "儲存失敗", "設定未完整儲存，請稍後再試。")
            return

        self.close()

    def confirm_clear_history(self):
        result = QMessageBox.question(
            self,
            "確認刪除對話紀錄",
            "確定要刪除所有對話紀錄嗎？這個動作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        settings_service.clear_history()
        QMessageBox.information(self, "已刪除", "對話紀錄已清空。")
