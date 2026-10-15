"""API group form: widget state and raw input events only."""
import os

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QBoxLayout, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget, QSizePolicy,
)

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.contracts.settings import APIKeyInput, APIGroupInput, APIGroupsInput, GroupTestInputs
from ui.settings.widgets.number_input import DecimalInput
from ui.settings.widgets.input_controls import NoWheelCheckBox, NoWheelComboBox, ToggleSwitch


class APIGroupEditor(QWidget):
    settings_changed = Signal(object)
    test_requested = Signal(str, str)
    add_group_requested = Signal()
    add_key_requested = Signal(str)
    delete_group_requested = Signal(str)
    RESPONSIVE_WIDTH = 600

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self.generation = 0
        self._active_id = None
        self._selected_id = None
        self._schema_version = 1
        self._narrow = False
        self.group_rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        master_detail = QBoxLayout(QBoxLayout.LeftToRight)
        master_detail.setSpacing(14)
        self.master_detail_layout = master_detail
        self.group_list_pane = QWidget()
        self.group_list_pane.setObjectName("settingsApiGroupList")
        self.group_list_pane.setMinimumWidth(180)
        self.group_list_pane.setMaximumWidth(230)
        list_layout = QVBoxLayout(self.group_list_pane)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(8)
        list_heading = QLabel("API 管理")
        list_heading.setObjectName("settingsSectionTitle")
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
        self.detail_stack.setObjectName("settingsApiGroupDetails")
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_label = QLabel("尚未建立 API 群組。請從左側新增一個群組。")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setWordWrap(True)
        empty_label.setObjectName("settingsPlaceholderStatus")
        empty_layout.addWidget(empty_label)
        self.empty_detail = empty
        self.detail_stack.addWidget(empty)
        master_detail.addWidget(self.detail_stack, 1)
        layout.addLayout(master_detail)
        self.state_label = QLabel()
        self.state_label.setTextFormat(Qt.PlainText)
        self.state_label.setWordWrap(True)
        self.state_label.setObjectName("settingsPageDescription")
        layout.addWidget(self.state_label)
        self._update_responsive_layout()

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
        if group is None:
            self.add_group_requested.emit()
            return self.group_for_id(self._selected_id)
        is_new = not self._loading
        list_button = QPushButton()
        list_button.setCheckable(True)
        list_button.setObjectName("settingsApiGroupButton")
        list_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        list_button.setMinimumHeight(58)
        list_button.setAccessibleName(f"編輯 API 群組 {group.name}")
        self.group_list_layout.addWidget(list_button)
        container = QWidget()
        container.setObjectName("settingsApiGroupDetailsContent")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary_card = QWidget()
        summary_card.setObjectName("settingsCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel()
        title.setObjectName("settingsSectionTitle")
        title.setWordWrap(True)
        active_badge = QLabel("目前使用")
        active_badge.setObjectName("settingsStatusBadge")
        edit_button = QPushButton("編輯")
        edit_button.setObjectName("settingsApiGroupEditButton")
        edit_button.setCheckable(True)
        more_button = QPushButton("⋯")
        more_button.setAccessibleName("群組其他操作")
        more_button.setToolTip("其他操作")
        more_button.setFixedWidth(42)
        group_menu = QMenu(more_button)
        active_action = group_menu.addAction("設為目前使用")
        delete_action = group_menu.addAction("刪除群組")
        more_button.setMenu(group_menu)
        header.addWidget(title, 1)
        header.addWidget(active_badge)
        header.addWidget(edit_button)
        header.addWidget(more_button)
        summary_layout.addLayout(header)
        summary_url = QLabel()
        summary_url.setObjectName("settingsSummaryPrimary")
        summary_url.setWordWrap(True)
        summary_meta = QLabel()
        summary_meta.setObjectName("settingsPageDescription")
        summary_meta.setWordWrap(True)
        summary_layout.addWidget(summary_url)
        summary_layout.addWidget(summary_meta)
        layout.addWidget(summary_card)

        group_edit_body = QWidget()
        group_edit_body.setObjectName("settingsCard")
        group_edit_layout = QVBoxLayout(group_edit_body)
        group_edit_layout.setContentsMargins(18, 16, 18, 16)
        group_edit_layout.setSpacing(10)
        group_edit_heading = QLabel("群組設定")
        group_edit_heading.setObjectName("settingsSectionTitle")
        group_edit_layout.addWidget(group_edit_heading)
        group_form = QFormLayout()
        group_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        group_form.setSpacing(12)
        name = QLineEdit(group.name)
        url = QLineEdit(group.base_url)
        url_note = QLabel("請填 API 根路徑，程式會自動附加 /chat/completions。")
        url_note.setObjectName("settingsPageDescription")
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
        for label, control in (("群組名稱：", name), ("Base URL：", url), ("驗證模式：", mode)):
            control.setAccessibleName(label.rstrip("："))
            group_form.addRow(label, control)
            if control is url:
                group_form.addRow("", url_note)
        group_form.addRow(ssl)
        group_edit_layout.addLayout(group_form)
        test_button = QPushButton("測試免金鑰連線")
        test_status = QLabel()
        test_status.setTextFormat(Qt.PlainText)
        test_status.setWordWrap(True)
        test_note = QLabel("連線測試會送出真實請求，可能產生服務費用。")
        test_note.setObjectName("settingsPageDescription")
        test_note.setWordWrap(True)
        group_edit_layout.addWidget(test_button)
        group_edit_layout.addWidget(test_note)
        group_edit_layout.addWidget(test_status)
        group_edit_body.hide()
        layout.addWidget(group_edit_body)

        model_card = QWidget()
        model_card.setObjectName("settingsCard")
        model_layout = QVBoxLayout(model_card)
        model_layout.setContentsMargins(18, 16, 18, 16)
        model_layout.setSpacing(10)
        model_heading = QLabel("模型設定")
        model_heading.setObjectName("settingsSectionTitle")
        model_layout.addWidget(model_heading)
        model_form = QFormLayout()
        model_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        model_form.setSpacing(12)
        for label, control in (("模型：", model), ("溫度：", temperature)):
            control.setAccessibleName(label.rstrip("："))
            model_form.addRow(label, control)
        model_layout.addLayout(model_form)
        layout.addWidget(model_card)

        key_card = QWidget()
        key_card.setObjectName("settingsCard")
        key_card_layout = QVBoxLayout(key_card)
        key_card_layout.setContentsMargins(18, 16, 18, 16)
        key_card_layout.setSpacing(10)
        key_header = QHBoxLayout()
        key_count = QLabel()
        key_count.setObjectName("settingsSectionTitle")
        key_header.addWidget(key_count, 1)
        add_key = QPushButton("新增 Key")
        key_header.addWidget(add_key)
        key_card_layout.addLayout(key_header)
        key_layout = QVBoxLayout()
        key_layout.setSpacing(8)
        key_card_layout.addLayout(key_layout)
        layout.addWidget(key_card)
        row = {"id": group.id, "container": container, "toggle": edit_button,
               "title": title, "advanced_button": edit_button, "advanced_body": group_edit_body,
               "name": name, "url": url, "model": model, "temperature": temperature,
               "ssl": ssl, "mode": mode, "keys": [], "key_layout": key_layout,
               "active_action": active_action, "delete_action": delete_action, "add_key": add_key,
               "list_button": list_button, "url_note": url_note, "key_count": key_count,
               "active_badge": active_badge, "summary_url": summary_url,
               "summary_meta": summary_meta, "more_button": more_button,
               "summary_card": summary_card, "model_card": model_card, "key_card": key_card}
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
        list_button.clicked.connect(lambda: self.select_group(group.id))
        edit_button.toggled.connect(
            lambda checked: self._set_advanced_visible(row, checked)
        )
        active_action.triggered.connect(lambda: self.set_active(group.id))
        delete_action.triggered.connect(lambda: self.confirm_delete_group(group.id))
        add_key.clicked.connect(lambda: self.add_key(group.id))
        for control in (name, url, model):
            control.textChanged.connect(self._changed)
        temperature.valueChanged.connect(self._changed)
        ssl.toggled.connect(self._changed)
        mode.currentIndexChanged.connect(self._changed)
        self._changed()
        self._arrange_all_keys()
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
        if entry is None:
            self.add_key_requested.emit(group_id)
            return group["keys"][-1] if group["keys"] else None
        container = QWidget()
        container.setObjectName("settingsApiKeyRow")
        layout = QGridLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(7)
        name = QLineEdit(entry.name)
        name.setPlaceholderText("Key 名稱")
        name.setAccessibleName("Key 名稱")
        source = NoWheelComboBox()
        source.addItem("儲存金鑰", "stored")
        source.addItem("環境變數 OPENAI_API_KEY", "environment")
        source.setCurrentIndex(source.findData(entry.source))
        source_badge = QLabel("環境變數")
        source_badge.setObjectName("settingsStatusBadge")
        saved_key = (os.environ.get(entry.environment_variable, "")
                     if self._schema_version == 2 and entry.source == "stored"
                     and entry.environment_variable and not entry.key else "")
        key = QLineEdit(entry.key or saved_key)
        key.setEchoMode(QLineEdit.Password)
        key.setAccessibleName("群組 API Key")
        if self._schema_version == 2 and entry.source == "stored" and entry.environment_variable:
            key.setPlaceholderText("已保存引用；留空表示保留原金鑰")
        show = QPushButton("顯示")
        show.setMinimumWidth(max(show.sizeHint().width(),
                                 show.fontMetrics().horizontalAdvance("隱藏") + 32))
        key_widget = QWidget()
        key_fields = QHBoxLayout(key_widget)
        key_fields.setContentsMargins(0, 0, 0, 0)
        key_fields.addWidget(key, 1)
        key_fields.addWidget(show)
        priority = NoWheelComboBox()
        for value in range(1, 11):
            priority.addItem(str(value), value)
        priority.setCurrentIndex(priority.findData(entry.priority))
        priority.setAccessibleName("Key 優先順位")
        priority_widget = QWidget()
        priority_fields = QHBoxLayout(priority_widget)
        priority_fields.setContentsMargins(0, 0, 0, 0)
        priority_fields.setSpacing(6)
        priority_fields.addWidget(QLabel("順位"))
        priority_fields.addWidget(priority)
        enabled = ToggleSwitch()
        enabled.setAccessibleName("啟用 Key")
        enabled.setToolTip("切換此 Key 是否參與正式請求")
        enabled.setChecked(entry.enabled)
        enabled_text = QLabel()
        enabled_widget = QWidget()
        enabled_fields = QHBoxLayout(enabled_widget)
        enabled_fields.setContentsMargins(0, 0, 0, 0)
        enabled_fields.setSpacing(7)
        enabled_fields.addWidget(enabled)
        enabled_fields.addWidget(enabled_text)
        more = QPushButton("⋯")
        more.setAccessibleName("Key 其他操作")
        more.setToolTip("其他操作")
        more.setFixedWidth(42)
        menu = QMenu(more)
        more_settings_action = menu.addAction("顯示更多設定")
        more_settings_action.setCheckable(True)
        menu.addSeparator()
        delete_action = menu.addAction("刪除 Key")
        more.setMenu(menu)
        status = QLabel()
        status.setObjectName("settingsPageDescription")
        status.setWordWrap(True)
        test_button = QPushButton("測試")
        test_status = QLabel()
        test_status.setTextFormat(Qt.PlainText)
        test_status.setWordWrap(True)
        test_status.hide()
        actions_widget = QWidget()
        actions = QHBoxLayout(actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(test_button)
        actions.addWidget(more)
        extra_body = QWidget()
        extra_layout = QFormLayout(extra_body)
        extra_layout.setContentsMargins(0, 4, 0, 0)
        extra_layout.setSpacing(8)
        extra_layout.addRow("金鑰來源：", source)
        extra_layout.addRow("", status)
        extra_body.hide()
        row = {"id": entry.id, "container": container, "name": name, "source": source,
               "original_source": entry.source, "environment_variable": entry.environment_variable,
               "key": key, "displayed_saved_key": saved_key, "initial_key_text": key.text(), "show": show,
               "priority": priority, "enabled": enabled,
               "enabled_text": enabled_text, "enabled_widget": enabled_widget, "status": status,
               "more": more, "delete_action": delete_action, "layout": layout,
               "key_widget": key_widget, "priority_widget": priority_widget,
               "actions_widget": actions_widget,
               "test_status": test_status, "source_badge": source_badge,
               "more_settings_action": more_settings_action, "extra_body": extra_body}
        group["keys"].append(row)
        row.update(test_button=test_button, test_status=test_status, testing=False)
        test_button.clicked.connect(lambda: self.test_requested.emit(group_id, entry.id))
        group["key_layout"].addWidget(container)
        self._arrange_key(row, self._narrow)

        def update_source(*_args):
            is_stored = source.currentData() == "stored"
            key.setEnabled(is_stored)
            show.setEnabled(is_stored)
            if not is_stored:
                key.setEchoMode(QLineEdit.Password)
                show.setText("顯示")
            source_badge.setVisible(not is_stored)
            enabled_text.setText("啟用中" if enabled.isChecked() else "已停用")
            self._changed()

        def reveal():
            visible = key.echoMode() == QLineEdit.Password
            key.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
            show.setText("隱藏" if visible else "顯示")

        show.clicked.connect(reveal)
        more_settings_action.toggled.connect(
            lambda checked: self._set_key_details_visible(row, checked)
        )
        for control in (name, key):
            control.textChanged.connect(self._changed)
        priority.currentIndexChanged.connect(self._changed)
        enabled.toggled.connect(update_source)
        source.currentIndexChanged.connect(update_source)
        delete_action.triggered.connect(lambda: self.remove_key(group_id, entry.id))
        update_source()
        return row

    @staticmethod
    def _set_key_details_visible(row, visible):
        row["extra_body"].setVisible(visible)
        row["more_settings_action"].setText(
            "隱藏更多設定" if visible else "顯示更多設定"
        )

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
        self.delete_group_requested.emit(group_id)

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

    def show_feedback(self, feedback):
        self.state_label.setText(feedback.status)
        self.state_label.setVisible(bool(feedback.status))
        for row in self.group_rows:
            duplicate = row["id"] in feedback.completion_path_groups
            row["url_note"].setText(
                "請移除 /chat/completions；程式會自動附加此路徑。"
                if duplicate else "請填 API 根路徑，程式會自動附加 /chat/completions。"
            )
            row["url_note"].setProperty("validationError", duplicate)
            row["url_note"].setStyleSheet("color: #b3261e; font-weight: 600;" if duplicate else "")
            if duplicate:
                row["advanced_button"].setChecked(True)
            for entry in row["keys"]:
                if entry["source"].currentData() == "environment":
                    text = "環境來源已設定（不顯示或保存內容）" if feedback.environment_available else "環境來源尚無值"
                elif self._schema_version == 2 and entry["environment_variable"] and not entry["key"].text():
                    text = "已保存引用；留空保留，刪除 Key 可清除"
                else:
                    text = "啟用" if entry["enabled"].isChecked() else "X：已暫停，原順位保留"
                entry["status"].setText(text)

    def _set_advanced_visible(self, row, visible):
        row["advanced_body"].setVisible(visible)
        row["advanced_button"].setText("完成" if visible else "編輯")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_layout(event.size().width())

    def set_available_width(self, width: int) -> None:
        """Let a containing viewport supply its usable content width."""
        self._update_responsive_layout(max(0, width))

    def _update_responsive_layout(self, width=None):
        narrow = (self.width() if width is None else width) < self.RESPONSIVE_WIDTH
        if narrow == self._narrow and width is not None:
            return
        self._narrow = narrow
        self.master_detail_layout.setDirection(
            QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        )
        self.group_list_pane.setMinimumWidth(0 if narrow else 180)
        self.group_list_pane.setMaximumWidth(16777215 if narrow else 230)
        self._arrange_all_keys()

    def _arrange_all_keys(self):
        for group in self.group_rows:
            for entry in group["keys"]:
                self._arrange_key(entry, self._narrow)

    @staticmethod
    def _arrange_key(row, narrow):
        layout = row["layout"]
        while layout.count():
            layout.takeAt(0)
        if narrow:
            for line, widget in enumerate((row["name"], row["source_badge"], row["key_widget"],
                                           row["priority_widget"], row["enabled_widget"], row["actions_widget"],
                                           row["extra_body"], row["test_status"])):
                layout.addWidget(widget, line, 0)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 0)
            layout.setColumnStretch(2, 0)
        else:
            layout.addWidget(row["name"], 0, 0)
            layout.addWidget(row["source_badge"], 0, 1)
            layout.addWidget(row["enabled_widget"], 0, 2)
            layout.addWidget(row["key_widget"], 1, 0, 1, 2)
            layout.addWidget(row["priority_widget"], 1, 2)
            layout.addWidget(row["actions_widget"], 2, 2)
            layout.addWidget(row["extra_body"], 3, 0, 1, 3)
            layout.addWidget(row["test_status"], 4, 0, 1, 3)
            layout.setColumnStretch(0, 2)
            layout.setColumnStretch(1, 2)
            layout.setColumnStretch(2, 1)

    def connection_inputs(self) -> GroupTestInputs:
        targets = {(group["id"], "") for group in self.group_rows}
        targets.update((group["id"], key["id"])
                       for group in self.group_rows for key in group["keys"])
        return GroupTestInputs(self.generation, frozenset(targets))

    def collect_input(self) -> APIGroupsInput:
        """Raw input port; phase three will switch the live change signal to it."""
        groups = []
        for row in self.group_rows:
            keys = tuple(APIKeyInput(
                entry["id"], entry["name"].text(), entry["key"].text(),
                entry["priority"].currentData(), entry["enabled"].isChecked(),
                entry["source"].currentData(),
                entry["key"].text() != entry["initial_key_text"],
            ) for entry in row["keys"])
            groups.append(APIGroupInput(
                row["id"], row["name"].text(), row["url"].text(), row["model"].text(),
                row["temperature"].value(), row["ssl"].isChecked(),
                row["mode"].currentData(), keys,
                row["temperature"].value() != row["display_temperature"],
            ))
        return APIGroupsInput(tuple(groups), self._active_id)

    def collect_settings(self):
        """Legacy conversion; replaced by application-side editing in phase three."""
        groups = []
        for row in self.group_rows:
            keys = tuple(APIGroupKey(
                entry["id"], entry["name"].text(),
                ("" if self._schema_version == 2 and entry["original_source"] == "stored"
                 and entry["key"].text() == entry["displayed_saved_key"]
                 else entry["key"].text()),
                entry["priority"].currentData(), entry["enabled"].isChecked(),
                entry["source"].currentData(),
                ("OPENAI_API_KEY" if entry["source"].currentData() == "environment" else
                 entry["environment_variable"] if entry["original_source"] == "stored" else ""),
            ) for entry in row["keys"])
            groups.append(APIGroup(
                row["id"], row["name"].text(), row["url"].text(), row["model"].text(),
                (row["original_temperature"] if row["temperature"].value() == row["display_temperature"]
                 else row["temperature"].value()),
                row["ssl"].isChecked(), row["mode"].currentData(), keys,
            ))
        return APIGroupSettings(tuple(groups), self._active_id, self._schema_version)

    def commit_pending_input(self):
        for group in self.group_rows:
            group["temperature"].interpretText()

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
            row["test_status"].setVisible(bool(message))
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
            name = row["name"].text().strip() or "未命名"
            row["title"].setText(name)
            row["active_badge"].setVisible(active)
            row["summary_url"].setText(row["url"].text().strip() or "尚未設定網址")
            ssl_text = "SSL 驗證開啟" if row["ssl"].isChecked() else "SSL 驗證關閉"
            auth_text = "免金鑰" if group.auth_mode == "none" else "使用 API Key"
            row["summary_meta"].setText(
                f"{row['model'].text().strip() or '尚未設定模型'}  ·  {auth_text}  ·  {ssl_text}"
            )
            row["container"].setProperty("editingSelected", selected)
            row["list_button"].setChecked(selected)
            row["list_button"].setProperty("activeGroup", active)
            row["list_button"].setText(
                f"{'● ' if active else ''}{name}"
                f"{' · 目前使用' if active else ''}"
                f"{' · 編輯中' if selected else ''}\n"
                f"{row['url'].text().strip() or '尚未設定網址'}"
            )
            row["list_button"].setAccessibleName(
                f"編輯 API 群組 {name}"
                + ("，目前使用" if active else "")
            )
            row["active_action"].setEnabled(not active)
            none = group.auth_mode == "none"
            row["test_button"].setVisible(none)
            row["test_button"].setEnabled(none and not row["testing"])
            row["add_key"].setEnabled(not none)
            row["key_count"].setText(f"API Keys（{len(row['keys'])}）")
            for entry in row["keys"]:
                entry["container"].setEnabled(not none and not entry["testing"])
                entry["test_button"].setEnabled(not none and not entry["testing"])
        selected_row = self.group_for_id(self._selected_id)
        self.detail_stack.setCurrentWidget(selected_row["container"] if selected_row else self.empty_detail)
