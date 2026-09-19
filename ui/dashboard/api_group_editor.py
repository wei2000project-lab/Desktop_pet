"""Draft-only API group editor; persistence belongs to DashboardWindow."""
import os
from uuid import uuid4
from urllib.parse import urlsplit

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget, QSizePolicy,
)

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.settings.api_group_resolver import APIGroupResolutionError, resolve_api_request
from app.settings.model import SettingsValidationError
from ui.dashboard.number_input import DecimalInput, IntegerInput
from ui.dashboard.input_controls import NoWheelCheckBox, NoWheelComboBox


class APIGroupEditor(QWidget):
    settings_changed = Signal(object)
    test_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self.generation = 0
        self._active_id = None
        self._selected_id = None
        self._schema_version = 1
        self.group_rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        notice = QLabel("正式請求使用已儲存的目前群組；修改後請按套用。連線測試使用草稿、不自動儲存，會發送請求並可能消耗額度。X 金鑰仍可手動測試。")
        notice.setObjectName("dashboardPlaceholderStatus")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        master_detail = QHBoxLayout()
        master_detail.setSpacing(14)
        self.group_list_pane = QWidget()
        self.group_list_pane.setObjectName("dashboardApiGroupList")
        self.group_list_pane.setMinimumWidth(180)
        self.group_list_pane.setMaximumWidth(230)
        list_layout = QVBoxLayout(self.group_list_pane)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(8)
        list_heading = QLabel("API 管理")
        list_heading.setObjectName("dashboardSectionTitle")
        list_layout.addWidget(list_heading)
        self.add_group_button = QPushButton("新增 API 群組")
        self.add_group_button.clicked.connect(lambda: self.add_group())
        list_layout.addWidget(self.add_group_button)
        self.group_list_layout = QVBoxLayout()
        self.group_list_layout.setSpacing(6)
        list_layout.addLayout(self.group_list_layout)
        list_layout.addStretch(1)
        master_detail.addWidget(self.group_list_pane)

        self.detail_stack = QStackedWidget()
        self.detail_stack.setObjectName("dashboardApiGroupDetails")
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_label = QLabel("尚未建立 API 群組。請從左側新增一個群組。")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setWordWrap(True)
        empty_label.setObjectName("dashboardPlaceholderStatus")
        empty_layout.addWidget(empty_label)
        self.empty_detail = empty
        self.detail_stack.addWidget(empty)
        master_detail.addWidget(self.detail_stack, 1)
        layout.addLayout(master_detail)
        self.state_label = QLabel()
        self.state_label.setTextFormat(Qt.PlainText)
        self.state_label.setWordWrap(True)
        self.state_label.setObjectName("dashboardPageDescription")
        layout.addWidget(self.state_label)

    def load_settings(self, settings: APIGroupSettings):
        self.generation += 1
        previous_selection = self._selected_id
        self._loading = True
        try:
            self._active_id = settings.active_group_id
            self._schema_version = settings.schema_version
            for row in self.group_rows:
                self.detail_stack.removeWidget(row["container"])
                self.group_list_layout.removeWidget(row["list_button"])
                row["container"].hide()
                row["container"].deleteLater()
                row["list_button"].hide()
                row["list_button"].deleteLater()
            self.group_rows = []
            for group in settings.groups:
                self.add_group(group)
        finally:
            self._loading = False
        available = {row["id"] for row in self.group_rows}
        if previous_selection in available:
            self._selected_id = previous_selection
        elif settings.active_group_id in available:
            self._selected_id = settings.active_group_id
        else:
            self._selected_id = self.group_rows[0]["id"] if self.group_rows else None
        self._update_titles()

    def add_group(self, group=None):
        is_new = group is None
        if group is None:
            group = APIGroup(str(uuid4()), "新 API 群組", "https://api.openai.com/v1", "gpt-4o-mini")
        list_button = QPushButton()
        list_button.setCheckable(True)
        list_button.setObjectName("dashboardApiGroupButton")
        list_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        list_button.setMinimumHeight(58)
        list_button.setAccessibleName(f"編輯 API 群組 {group.name}")
        self.group_list_layout.addWidget(list_button)
        container = QWidget()
        container.setObjectName("dashboardSettingsCard")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 16, 18, 16)
        header = QHBoxLayout()
        toggle = QPushButton()
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        toggle.setToolTip("展開或收合群組")
        active_button = QPushButton("設為目前使用")
        delete_button = QPushButton("刪除群組")
        delete_button.setObjectName("dashboardDangerButton")
        header.addWidget(toggle, 1)
        header.addWidget(active_button)
        header.addWidget(delete_button)
        layout.addLayout(header)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 8, 0, 0)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setSpacing(12)
        name = QLineEdit(group.name)
        url = QLineEdit(group.base_url)
        url_note = QLabel("請填 API 根路徑，程式會自動附加 /chat/completions。")
        url_note.setObjectName("dashboardPageDescription")
        url_note.setWordWrap(True)
        model = QLineEdit(group.model)
        temperature = DecimalInput()
        temperature.setDecimals(max(1, len(f"{group.temperature:.12f}".split(".")[1].rstrip("0"))))
        temperature.setRange(0, 2)
        temperature.setSingleStep(0.1)
        temperature.setValue(group.temperature)
        ssl = NoWheelCheckBox("驗證 SSL 憑證")
        ssl.setChecked(group.verify_ssl)
        mode = NoWheelComboBox()
        mode.addItem("使用 API Key", "api_key")
        mode.addItem("免金鑰連線", "none")
        mode.setCurrentIndex(mode.findData(group.auth_mode))
        for label, control in (("群組名稱：", name), ("Base URL：", url), ("模型：", model),
                               ("溫度：", temperature), ("驗證模式：", mode)):
            control.setAccessibleName(label.rstrip("："))
            form.addRow(label, control)
            if control is url:
                form.addRow("", url_note)
        form.addRow(ssl)
        body_layout.addLayout(form)
        test_button = QPushButton("測試免金鑰連線")
        test_status = QLabel()
        test_status.setTextFormat(Qt.PlainText)
        test_status.setWordWrap(True)
        body_layout.addWidget(test_button)
        body_layout.addWidget(test_status)
        key_layout = QVBoxLayout()
        body_layout.addLayout(key_layout)
        add_key = QPushButton("新增 Key")
        body_layout.addWidget(add_key)
        key_note = QLabel("X 表示暫停自動使用；免金鑰模式不會使用任何 Key，但會保留列表。")
        key_note.setObjectName("dashboardPageDescription")
        key_note.setWordWrap(True)
        body_layout.addWidget(key_note)
        layout.addWidget(body)
        row = {"id": group.id, "container": container, "toggle": toggle, "body": body,
               "name": name, "url": url, "model": model, "temperature": temperature,
               "ssl": ssl, "mode": mode, "keys": [], "key_layout": key_layout,
               "active_button": active_button, "delete_button": delete_button, "add_key": add_key,
               "list_button": list_button, "url_note": url_note}
        row["original_temperature"] = group.temperature
        row.update(test_button=test_button, test_status=test_status, testing=False)
        test_button.clicked.connect(lambda: self.test_requested.emit(group.id, ""))
        row["display_temperature"] = temperature.value()
        self.group_rows.append(row)
        if is_new and not self._loading:
            self._selected_id = group.id
        self.detail_stack.addWidget(container)
        for entry in group.keys:
            self.add_key(group.id, entry)
        toggle.toggled.connect(body.setVisible)
        list_button.clicked.connect(lambda: self.select_group(group.id))
        active_button.clicked.connect(lambda: self.set_active(group.id))
        delete_button.clicked.connect(lambda: self.confirm_delete_group(group.id))
        add_key.clicked.connect(lambda: self.add_key(group.id))
        for control in (name, url, model):
            control.textChanged.connect(self._changed)
        url.textChanged.connect(lambda: self._update_url_note(row))
        temperature.valueChanged.connect(self._changed)
        ssl.toggled.connect(self._changed)
        mode.currentIndexChanged.connect(self._changed)
        self._changed()
        self._update_url_note(row)
        return row

    @property
    def selected_group_id(self):
        return self._selected_id

    def select_group(self, group_id):
        if self.group_for_id(group_id) is None:
            return
        self._selected_id = group_id
        self._update_titles()

    def group_for_id(self, group_id):
        return next((row for row in self.group_rows if row["id"] == group_id), None)

    def add_key(self, group_id, entry=None):
        group = self.group_for_id(group_id)
        if group is None:
            return
        entry = entry or APIGroupKey(str(uuid4()), "", "")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 6)
        fields = QFormLayout()
        fields.setRowWrapPolicy(QFormLayout.WrapLongRows)
        name = QLineEdit(entry.name)
        name.setPlaceholderText("Key 名稱")
        name.setAccessibleName("Key 名稱")
        source = NoWheelComboBox()
        source.addItem("儲存金鑰", "stored")
        source.addItem("環境變數 OPENAI_API_KEY", "environment")
        source.setCurrentIndex(source.findData(entry.source))
        key = QLineEdit(entry.key)
        key.setEchoMode(QLineEdit.Password)
        key.setAccessibleName("群組 API Key")
        show = QPushButton("顯示")
        show.setCheckable(True)
        key_fields = QHBoxLayout()
        key_fields.addWidget(key, 1)
        key_fields.addWidget(show)
        priority = IntegerInput()
        priority.setRange(1, 10)
        priority.setSingleStep(1)
        priority.setValue(entry.priority)
        priority.setAccessibleName("Key 優先順位")
        enabled = NoWheelCheckBox("啟用（取消即 X）")
        enabled.setChecked(entry.enabled)
        remove = QPushButton("刪除 Key")
        remove.setObjectName("dashboardDangerButton")
        status = QLabel()
        status.setObjectName("dashboardPageDescription")
        status.setWordWrap(True)
        fields.addRow("名稱：", name)
        fields.addRow("來源：", source)
        fields.addRow("金鑰：", key_fields)
        fields.addRow("順位：", priority)
        fields.addRow(enabled)
        layout.addLayout(fields)
        layout.addWidget(status)
        test_button = QPushButton("測試此 Key")
        test_status = QLabel()
        test_status.setTextFormat(Qt.PlainText)
        test_status.setWordWrap(True)
        layout.addWidget(test_button)
        layout.addWidget(test_status)
        layout.addWidget(remove)
        row = {"id": entry.id, "container": container, "name": name, "source": source,
               "key": key, "show": show, "priority": priority, "enabled": enabled, "status": status}
        group["keys"].append(row)
        row.update(test_button=test_button, test_status=test_status, testing=False)
        test_button.clicked.connect(lambda: self.test_requested.emit(group_id, entry.id))
        group["key_layout"].addWidget(container)

        def update_source(*_args):
            is_stored = source.currentData() == "stored"
            key.setEnabled(is_stored)
            show.setEnabled(is_stored)
            if not is_stored:
                show.setChecked(False)
            available = bool(os.environ.get("OPENAI_API_KEY", "").strip()) if not is_stored else False
            status.setText(("環境來源已設定（不顯示或保存內容）" if available else "環境來源尚無值") if not is_stored
                           else ("啟用" if enabled.isChecked() else "X：已暫停，原順位保留"))
            self._changed()

        def reveal(checked):
            key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
            show.setText("隱藏" if checked else "顯示")

        show.toggled.connect(reveal)
        for control in (name, key):
            control.textChanged.connect(self._changed)
        priority.valueChanged.connect(self._changed)
        enabled.toggled.connect(update_source)
        source.currentIndexChanged.connect(update_source)
        remove.clicked.connect(lambda: self.remove_key(group_id, entry.id))
        update_source()
        return row

    def remove_key(self, group_id, key_id):
        group = self.group_for_id(group_id)
        if group is None:
            return
        row = next((row for row in group["keys"] if row["id"] == key_id), None)
        if row is None:
            return
        group["keys"].remove(row)
        group["key_layout"].removeWidget(row["container"])
        row["container"].hide()
        row["container"].deleteLater()
        self._changed()

    def set_active(self, group_id):
        if self.group_for_id(group_id) is not None:
            self._active_id = group_id
            self._changed()

    def confirm_delete_group(self, group_id):
        active = group_id == self._active_id
        message = "確定刪除此群組及其金鑰嗎？"
        if active:
            message += "目前群組將變為未設定，請再選擇替代群組。"
        if QMessageBox.question(self, "刪除 API 群組", message,
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.remove_group(group_id)

    def remove_group(self, group_id):
        row = self.group_for_id(group_id)
        if row is None:
            return
        index = self.group_rows.index(row)
        self.group_rows.remove(row)
        self.detail_stack.removeWidget(row["container"])
        self.group_list_layout.removeWidget(row["list_button"])
        row["container"].hide()
        row["container"].deleteLater()
        row["list_button"].hide()
        row["list_button"].deleteLater()
        if self._active_id == group_id:
            self._active_id = None
        if self._selected_id == group_id:
            self._selected_id = (self.group_rows[min(index, len(self.group_rows) - 1)]["id"]
                                 if self.group_rows else None)
        self._changed()

    def validate_draft(self):
        for row in self.group_rows:
            path = urlsplit(row["url"].text().strip()).path.rstrip("/").lower()
            if path.endswith("/chat/completions"):
                raise SettingsValidationError(
                    "Base URL 請填 API 根路徑，不要包含 /chat/completions。"
                )

    def _update_url_note(self, row):
        path = urlsplit(row["url"].text().strip()).path.rstrip("/").lower()
        duplicate = path.endswith("/chat/completions")
        row["url_note"].setText(
            "請移除 /chat/completions；程式會自動附加此路徑。"
            if duplicate else "請填 API 根路徑，程式會自動附加 /chat/completions。"
        )
        row["url_note"].setProperty("validationError", duplicate)

    def collect_settings(self):
        groups = []
        for row in self.group_rows:
            keys = []
            for entry in row["keys"]:
                source = entry["source"].currentData()
                value = entry["key"].text().strip() if source == "stored" else ""
                if source == "stored" and not value:
                    continue
                keys.append(APIGroupKey(entry["id"], entry["name"].text().strip() or f"Key {len(keys) + 1}",
                                        value, entry["priority"].value(), entry["enabled"].isChecked(), source,
                                        "OPENAI_API_KEY" if source == "environment" else ""))
            groups.append(APIGroup(row["id"], row["name"].text().strip(), row["url"].text().strip(),
                                   row["model"].text().strip(),
                                   (row["original_temperature"] if row["temperature"].value() == row["display_temperature"]
                                    else row["temperature"].value()),
                                   row["ssl"].isChecked(), row["mode"].currentData(), tuple(keys)))
        return APIGroupSettings(tuple(groups), self._active_id, self._schema_version)

    def commit_pending_input(self):
        for group in self.group_rows:
            group["temperature"].interpretText()
            for entry in group["keys"]:
                entry["priority"].interpretText()

    def test_row(self, group_id, key_id):
        group = self.group_for_id(group_id)
        if group is None or not key_id:
            return group
        return next((row for row in group["keys"] if row["id"] == key_id), None)

    def set_test_status(self, group_id, key_id, message, testing=False):
        row = self.test_row(group_id, key_id)
        if row is not None:
            row["testing"] = testing
            row["test_status"].setText(message)
            self._update_titles()

    def _changed(self, *_args):
        if not self._loading:
            self._update_titles()
            self.settings_changed.emit(self.collect_settings())

    def _update_titles(self):
        settings = self.collect_settings()
        for row, group in zip(self.group_rows, settings.groups):
            active = row["id"] == self._active_id
            selected = row["id"] == self._selected_id
            enabled_count = sum(entry.enabled for entry in group.keys)
            mode = "免金鑰" if row["mode"].currentData() == "none" else f"啟用 Key：{enabled_count}"
            row["toggle"].setText(f"{row['name'].text().strip() or '未命名'} · {mode}"
                                  + (" · 目前群組" if active else "")
                                  + (" · 編輯中" if selected else ""))
            row["container"].setProperty("editingSelected", selected)
            row["list_button"].setChecked(selected)
            row["list_button"].setProperty("activeGroup", active)
            row["list_button"].setText(
                f"{'● ' if active else ''}{row['name'].text().strip() or '未命名'}"
                f"{' · 目前使用' if active else ''}\n"
                f"{row['url'].text().strip() or '尚未設定網址'}"
            )
            row["list_button"].setAccessibleName(
                f"編輯 API 群組 {row['name'].text().strip() or '未命名'}"
                + ("，目前使用" if active else "")
            )
            row["active_button"].setEnabled(not active)
            none = group.auth_mode == "none"
            row["test_button"].setVisible(none)
            row["test_button"].setEnabled(none and not row["testing"])
            for entry in row["keys"]:
                entry["test_button"].setEnabled(not none and not entry["testing"])
        selected_row = self.group_for_id(self._selected_id)
        self.detail_stack.setCurrentWidget(selected_row["container"] if selected_row else self.empty_detail)
        try:
            resolve_api_request(settings)
            status = "目前群組已具備發送所需設定（尚未測試連線）。"
        except APIGroupResolutionError as error:
            status = str(error)
        self.state_label.setText(status + " 草稿修改套用後才會影響新請求。")
