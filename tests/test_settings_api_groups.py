import configparser
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QGridLayout, QLineEdit, QMessageBox

from app.core.config_manager import ConfigManager
from app.settings import APIGroupService, SettingsService
from app.settings.api_groups import serialize_api_groups, validate_api_groups
from tests.settings_helpers import create_settings_window
from ui.settings.widgets.input_controls import NoWheelComboBox, ToggleSwitch
from tests.settings_helpers import FakePool, FakeWorker
from app.ai.client import AIClient


class SettingsAPIGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        environment = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = object.__new__(ConfigManager)
        self.store.api_groups_json_path = str(self.root / "api_groups.json")
        self.store.config_ini_path = str(self.root / "app.ini")
        self.store.tools_json_path = str(self.root / "tools.json")
        self.store.api_ini_path = str(self.root / "api.ini")
        self.store.prompt_json_path = str(self.root / "prompt.json")
        self.store.default_prompt_json_path = str(self.root / "missing.json")
        self.store.general_config = configparser.ConfigParser()
        self.store.general_config.read_dict({"General": {"Width": "250"}})
        self.store.api_config = configparser.ConfigParser()
        self.store.api_config.read_dict({"API": {"BaseUrl": "https://example.test/v1", "Model": "old-model",
                                                 "ApiKey": "fake-stored-key", "VerifySSL": "false"}})
        self.events = []
        self.settings = SettingsService(self.store, self.events.append)
        self.groups = APIGroupService(self.store, self.events.append)
        self.window, self.presenter = create_settings_window(settings_backend=self.settings, group_backend=self.groups)
        self.editor = self.window.ai_page.group_editor
        self.path = Path(self.store.api_groups_json_path)

    def tearDown(self):
        self.window._close_approved = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_initial_preview_is_clean_and_does_not_migrate_to_disk(self):
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertFalse(self.path.exists())
        group = self.presenter.session.groups.groups[0]
        self.assertEqual((group.base_url, group.model, group.verify_ssl), ("https://example.test/v1", "old-model", False))
        self.assertEqual(group.keys[0].key, "fake-stored-key")
        self.assertEqual(self.events, [])

    def test_edit_button_keeps_same_feedback_in_both_modes(self):
        self.window.select_page("ai")
        self.window.show()
        self.app.processEvents()
        button = self.editor.group_rows[0]["advanced_button"]

        def background():
            self.app.processEvents()
            return button.grab().toImage().pixelColor(8, button.height() // 2).name()

        states = []
        for checked in (False, True):
            button.setChecked(checked)
            QTest.mouseMove(self.window, QPoint(self.window.width() - 2, self.window.height() - 2))
            normal = background()
            QTest.mouseMove(button, QPoint(8, button.height() // 2))
            hover = background()
            QTest.mousePress(button, Qt.LeftButton, pos=QPoint(8, button.height() // 2))
            pressed = background()
            QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-8, -8))
            QTest.mouseMove(self.window, QPoint(self.window.width() - 2, self.window.height() - 2))
            self.assertEqual(background(), normal)
            states.append((normal, hover, pressed))

        self.assertEqual(states[0], states[1])
        self.assertEqual(len(set(states[0])), 3)
        self.assertEqual(button.text(), "完成")

    def start_test(self, key=True):
        controller = self.presenter.connection_tests
        controller.pool = FakePool()
        controller.worker_factory = FakeWorker
        group = self.editor.group_rows[0]
        row = group["keys"][0] if key else group
        controller.start_group(group["id"], row["id"] if key else "")
        return controller, group, row

    @staticmethod
    def wheel_event():
        return QWheelEvent(
            QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )

    def test_group_check_uses_draft_without_saving(self):
        controller, group, row = self.start_test()
        self.assertEqual(controller.pool.workers[0].inputs,
                         ("https://example.test/v1", "fake-stored-key", "old-model", False))
        self.assertFalse(row["test_button"].isEnabled())
        self.assertFalse(row["name"].isEnabled())
        self.assertFalse(self.path.exists())
        self.assertFalse(self.presenter.session.is_dirty)
        controller.pool.workers[0].finish()
        self.assertEqual(row["test_status"].text(), "連線測試成功。")
        self.assertTrue(row["test_button"].isEnabled())
        self.assertTrue(row["name"].isEnabled())

    def test_group_check_ignores_changed_draft(self):
        controller, group, row = self.start_test()
        group["model"].setText("changed")
        controller.pool.workers[0].finish()
        self.assertIn("設定已變更", row["test_status"].text())

    def test_group_check_ignores_rebuilt_rows(self):
        controller, group, row = self.start_test()
        self.presenter.render()
        controller.pool.workers[0].finish()
        self.assertEqual(self.editor.group_rows[0]["keys"][0]["test_status"].text(), "")
        self.assertEqual(controller._jobs, {})

    def test_group_check_ignores_deleted_group(self):
        controller, group, row = self.start_test()
        self.editor.remove_group(group["id"])
        controller.pool.workers[0].finish()
        self.assertEqual(controller._jobs, {})

    def test_group_check_ignores_closed_session(self):
        controller, group, row = self.start_test()
        controller.invalidate()
        controller.pool.workers[0].finish()
        self.assertNotEqual(row["test_status"].text(), "連線測試成功。")

    def test_disabled_key_can_be_manually_tested(self):
        self.editor.group_rows[0]["keys"][0]["enabled"].setChecked(False)
        controller, group, row = self.start_test()
        self.assertEqual(len(controller.pool.workers), 1)
        self.assertFalse(row["enabled"].isChecked())

    def test_environment_check_missing_and_present(self):
        row = self.editor.group_rows[0]["keys"][0]
        row["source"].setCurrentIndex(1)
        controller, group, row = self.start_test()
        self.assertEqual(controller.pool.workers, [])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-env-key"}):
            controller.start_group(group["id"], row["id"])
            self.assertEqual(controller.pool.workers[0].inputs[1], "synthetic-env-key")
        controller.pool.workers[0].finish()
        self.assertIn("設定已變更", row["test_status"].text())
        self.assertNotIn("synthetic-env-key", row["test_status"].text())

    def test_none_check_omits_credentials(self):
        self.editor.group_rows[0]["mode"].setCurrentIndex(1)
        controller, group, row = self.start_test(key=False)
        self.assertIsNone(controller.pool.workers[0].inputs[1])
        client = AIClient("https://example.test/v1", None, "model")
        self.assertNotIn("Authorization", client._build_headers())
        self.assertEqual(AIClient("https://example.test", "fake", "model")._build_headers()["Authorization"], "Bearer fake")
        session = Mock()
        session.post.return_value.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        with patch("app.ai.client.requests.Session", return_value=session):
            self.assertTrue(client.test_connection())
        self.assertNotIn("Authorization", session.post.call_args.kwargs["headers"])

    def test_group_check_duplicate_click_and_deleted_key(self):
        controller, group, row = self.start_test()
        controller.start_group(group["id"], row["id"])
        self.assertEqual(len(controller.pool.workers), 1)
        self.editor.remove_key(group["id"], row["id"])
        controller.pool.workers[0].finish()
        self.assertEqual(controller._jobs, {})

    def test_group_check_limit_and_submission_failure(self):
        controller, group, row = self.start_test()
        for _ in range(4):
            extra = self.editor.add_key(group["id"])
            extra["key"].setText("synthetic-key")
            controller.start_group(group["id"], extra["id"])
        self.assertEqual(len(controller.pool.workers), 4)
        self.assertIn("多個測試", extra["test_status"].text())
        for worker in controller.pool.workers:
            worker.finish()
        with patch.object(controller.pool, "start", side_effect=RuntimeError("private")):
            controller.start_group(group["id"], row["id"])
        self.assertEqual(controller._jobs, {})
        self.assertTrue(row["test_button"].isEnabled())
        self.assertNotIn("private", row["test_status"].text())

    def test_hidden_old_settings_do_not_change_legacy_data(self):
        self.window.ai_page.model_input.setText("new-old-model")
        self.assertTrue(self.presenter.apply_changes())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.get_api("Model"), "old-model")
        self.assertFalse(self.presenter.session.is_dirty)

    def test_formal_group_ui_hides_legacy_cards_and_keeps_memory(self):
        self.assertTrue(self.window.ai_page._group_mode)
        self.assertTrue(all(card.isHidden() for card in self.window.ai_page._legacy_cards))
        self.window.ai_page.max_memory_turns_input.setValue(3)
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(self.store.get_general_int("MaxMemoryTurns"), 3)
        self.assertFalse(self.path.exists())

    def test_group_apply_preserves_legacy_file_bytes(self):
        legacy = Path(self.store.api_ini_path)
        original = b"[API]\nModel=original-preserved\nApiKey=synthetic-original-key\n"
        # Test fixture only; create the original file through the production atomic writer.
        from app.core.config_manager import write_text_bundle_atomically
        write_text_bundle_atomically({legacy: original.decode()})
        self.editor.group_rows[0]["name"].setText("修改群組")
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(legacy.read_bytes(), original)

    def test_invalid_hidden_legacy_fields_do_not_block_group_save(self):
        self.store.api_config.set("API", "BaseUrl", "")
        self.store.api_config.set("API", "Model", "")
        self.presenter.session.snapshot = replace(self.presenter.session.snapshot, base_url="", model="")
        self.editor.group_rows[0]["name"].setText("有效群組")
        self.assertTrue(self.presenter.apply_changes())

    def test_rename_preserves_group_and_key_ids(self):
        row = self.editor.group_rows[0]
        original = self.presenter.session.groups
        row["name"].setText("重新命名")
        edited = self.presenter.session.groups
        self.assertEqual(edited.groups[0].id, original.groups[0].id)
        self.assertEqual(edited.groups[0].keys[0].id, original.groups[0].keys[0].id)
        self.assertEqual(edited.active_group_id, original.active_group_id)
        self.assertTrue(self.presenter.session.is_dirty)

    def test_add_has_valid_defaults_and_does_not_switch_active(self):
        active = self.presenter.session.groups.active_group_id
        row = self.editor.add_group()
        settings = self.presenter.session.groups
        validate_api_groups(settings)
        self.assertEqual(settings.active_group_id, active)
        self.assertNotEqual(row["id"], active)
        self.editor.set_active(row["id"])
        self.assertEqual(self.presenter.session.groups.active_group_id, row["id"])
        self.assertFalse(self.path.exists())

    def test_editing_selection_is_separate_from_active_group(self):
        active = self.presenter.session.groups.active_group_id
        added = self.editor.add_group()
        self.assertEqual(self.editor.selected_group_id, added["id"])
        self.assertEqual(self.presenter.session.groups.active_group_id, active)
        self.assertIn("編輯中", added["list_button"].text())
        draft = self.presenter.session.groups
        first = self.editor.group_rows[0]
        first["list_button"].click()
        self.assertEqual(self.editor.selected_group_id, first["id"])
        self.assertEqual(self.presenter.session.groups.active_group_id, active)
        self.assertEqual(self.presenter.session.groups, draft)

    def test_master_detail_shows_only_selected_group_and_keeps_drafts(self):
        first = self.editor.group_rows[0]
        second = self.editor.add_group()
        second["model"].setText("second-draft-model")
        self.assertIs(self.editor.detail_stack.currentWidget(), second["container"])
        self.assertTrue(second["list_button"].isChecked())
        first["list_button"].click()
        self.assertIs(self.editor.detail_stack.currentWidget(), first["container"])
        self.assertFalse(second["list_button"].isChecked())
        second["list_button"].click()
        self.assertEqual(second["model"].text(), "second-draft-model")

    def test_complete_chat_endpoint_is_explained_and_blocks_apply(self):
        row = self.editor.group_rows[0]
        row["url"].setText("https://example.test/v1/chat/completions/")
        self.assertIn("請移除", row["url_note"].text())
        self.assertFalse(row["advanced_body"].isHidden())
        with patch("ui.settings.settings_window.SettingsDialog.warning") as warning:
            self.assertFalse(self.presenter.apply_changes())
        self.assertIn("不要包含 /chat/completions", warning.call_args.args[2])
        self.assertTrue(self.presenter.session.is_dirty)

    def test_editing_selection_survives_reload_and_moves_after_delete(self):
        first = self.editor.group_rows[0]
        second = self.editor.add_group()
        settings = self.presenter.session.groups
        self.presenter.session.groups = settings
        self.presenter.render()
        self.assertEqual(self.editor.selected_group_id, second["id"])
        self.editor.remove_group(second["id"])
        self.assertEqual(self.editor.selected_group_id, first["id"])
        self.assertEqual(self.presenter.session.groups.active_group_id, first["id"])

    def test_collapsing_and_revealing_do_not_dirty(self):
        row = self.editor.group_rows[0]
        self.assertEqual(row["toggle"].text(), "編輯")
        row["toggle"].click()
        self.assertFalse(row["advanced_body"].isHidden())
        self.assertEqual(row["toggle"].text(), "完成")
        row["toggle"].click()
        self.assertTrue(row["advanced_body"].isHidden())
        key = row["keys"][0]
        key["show"].click()
        self.assertEqual(key["key"].echoMode(), QLineEdit.Normal)
        key["show"].click()
        self.assertEqual(key["key"].echoMode(), QLineEdit.Password)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_group_summary_replaces_always_visible_group_fields(self):
        row = self.editor.group_rows[0]
        self.assertTrue(row["advanced_body"].isHidden())
        self.assertEqual(row["title"].text(), "預設 API")
        self.assertEqual(row["summary_url"].text(), "https://example.test/v1")
        self.assertIn("old-model", row["summary_meta"].text())
        self.assertIn("使用 API Key", row["summary_meta"].text())
        self.assertFalse(row["active_badge"].isHidden())
        self.assertTrue(self.editor.state_label.isHidden())

        row["model"].setText("summary-model")
        row["ssl"].setChecked(True)
        self.assertIn("summary-model", row["summary_meta"].text())
        self.assertIn("SSL 驗證開啟", row["summary_meta"].text())

    def test_responsive_layout_reflows_master_detail_and_key_fields(self):
        row = self.editor.group_rows[0]
        key = row["keys"][0]
        self.editor._update_responsive_layout(800)
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.LeftToRight)
        wide_key_row = key["layout"].getItemPosition(key["layout"].indexOf(key["key_widget"]))[0]
        self.editor._update_responsive_layout(520)
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.TopToBottom)
        narrow_key_row = key["layout"].getItemPosition(key["layout"].indexOf(key["key_widget"]))[0]
        self.assertEqual(wide_key_row, 1)
        self.assertEqual(narrow_key_row, 2)
        self.assertEqual(self.editor.group_list_pane.maximumWidth(), 16777215)

    def test_key_source_is_hidden_in_more_settings_without_dirtying(self):
        key = self.editor.group_rows[0]["keys"][0]
        self.assertTrue(key["extra_body"].isHidden())
        self.assertTrue(key["source_badge"].isHidden())
        key["more_settings_action"].setChecked(True)
        self.assertFalse(key["extra_body"].isHidden())
        self.assertIn("隱藏", key["more_settings_action"].text())
        key["more_settings_action"].setChecked(False)
        self.assertTrue(key["extra_body"].isHidden())
        self.assertFalse(self.presenter.session.is_dirty)

        key["source"].setCurrentIndex(1)
        self.assertFalse(key["source_badge"].isHidden())
        self.assertEqual(key["source_badge"].text(), "環境變數")

    def test_settings_window_drives_wide_and_narrow_api_layouts(self):
        self.window.select_page("ai")
        self.window.show()
        self.window.resize(900, 760)
        self.app.processEvents()
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.LeftToRight)
        self.window.resize(650, 600)
        self.app.processEvents()
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.TopToBottom)
        self.assertEqual(self.window.ai_page.horizontalScrollBar().maximum(), 0)

    def test_priority_and_x_keep_previous_priority(self):
        key = self.editor.group_rows[0]["keys"][0]
        key["priority"].setCurrentIndex(key["priority"].findData(5))
        key["enabled"].setChecked(False)
        settings = self.presenter.session.groups
        self.assertFalse(settings.groups[0].keys[0].enabled)
        self.assertEqual(settings.groups[0].keys[0].priority, 5)
        key["enabled"].setChecked(True)
        self.assertEqual(self.presenter.session.groups.groups[0].keys[0].priority, 5)

    def test_key_priority_dropdown_and_toggle_switch(self):
        key = self.editor.group_rows[0]["keys"][0]
        self.assertIsInstance(key["priority"], NoWheelComboBox)
        self.assertEqual(
            [key["priority"].itemData(index) for index in range(key["priority"].count())],
            list(range(1, 11)),
        )
        self.assertIsInstance(key["enabled"], ToggleSwitch)
        initial = key["enabled"].isChecked()
        QTest.mouseClick(key["enabled"], Qt.LeftButton)
        self.assertNotEqual(key["enabled"].isChecked(), initial)
        self.assertEqual(
            key["enabled_text"].text(),
            "啟用中" if key["enabled"].isChecked() else "已停用",
        )

    def test_api_page_wheel_only_scrolls_and_finishes_active_input(self):
        self.window.show()
        self.window.resize(650, 600)
        self.window.select_page("ai")
        self.app.processEvents()
        group = self.editor.group_rows[0]
        key = group["keys"][0]
        temperature = group["temperature"]
        temperature.editor.setFocus()
        temperature.editor.lineEdit().setText("1.4")
        temperature.editor.lineEdit().selectAll()
        self.app.processEvents()

        QApplication.sendEvent(temperature.editor.lineEdit(), self.wheel_event())

        self.assertAlmostEqual(temperature.value(), 1.4)
        self.assertFalse(temperature.editor.hasFocus())
        self.assertEqual(temperature.editor.lineEdit().selectedText(), "")
        priority = key["priority"].currentData()
        enabled = key["enabled"].isChecked()
        QApplication.sendEvent(key["priority"], self.wheel_event())
        QApplication.sendEvent(key["enabled"], self.wheel_event())
        self.assertEqual(key["priority"].currentData(), priority)
        self.assertEqual(key["enabled"].isChecked(), enabled)

    def test_unavailable_active_group_is_clearly_marked(self):
        key = self.editor.group_rows[0]["keys"][0]
        key["enabled"].setChecked(False)
        self.assertIn("全部已暫停", self.editor.state_label.text())

    def test_unedited_legacy_temperature_precision_is_preserved(self):
        settings = self.presenter.session.groups
        settings = replace(settings, groups=(replace(settings.groups[0], temperature=0.75),))
        self.presenter.session.groups = settings
        self.presenter.render()
        self.assertEqual(self.editor.group_rows[0]["temperature"].value(), 0.75)
        self.editor.group_rows[0]["name"].setText("改名但不改溫度")
        self.assertEqual(self.presenter.session.groups.groups[0].temperature, 0.75)

    def test_blank_new_key_row_is_not_persisted_or_dirty(self):
        group = self.editor.group_rows[0]
        self.editor.add_key(group["id"])
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(len(self.presenter.session.groups.groups[0].keys), 1)
        self.assertEqual(group["key_count"].text(), "API Keys（2）")

    def test_key_uses_compact_grid_and_delete_menu(self):
        group = self.editor.group_rows[0]
        key = self.editor.add_key(group["id"])
        key["key"].setText("synthetic-second-key")
        self.assertIsInstance(key["container"].layout(), QGridLayout)
        self.assertTrue(key["more"].menu() is not None)
        self.assertEqual(group["key_count"].text(), "API Keys（2）")
        key["delete_action"].trigger()
        self.assertEqual(len(group["keys"]), 1)
        self.assertEqual(group["key_count"].text(), "API Keys（1）")

    def test_environment_reference_does_not_display_or_save_environment_secret(self):
        group = self.editor.group_rows[0]
        key = self.editor.add_key(group["id"])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-env-secret"}):
            key["source"].setCurrentIndex(1)
            settings = self.presenter.session.groups
            self.assertEqual(key["key"].text(), "")
            self.assertFalse(key["key"].isEnabled())
            self.assertFalse(key["show"].isEnabled())
            self.assertIn("已設定", key["status"].text())
            self.assertTrue(self.presenter.apply_changes())
        self.assertNotIn("fake-env-secret", serialize_api_groups(settings))
        self.assertNotIn("fake-env-secret", self.path.read_text(encoding="utf-8"))

    def test_none_mode_keeps_key_list(self):
        row = self.editor.group_rows[0]
        row["mode"].setCurrentIndex(1)
        settings = self.presenter.session.groups
        self.assertEqual(settings.groups[0].auth_mode, "none")
        self.assertEqual(settings.groups[0].keys[0].key, "fake-stored-key")
        self.assertFalse(row["add_key"].isEnabled())
        self.assertFalse(row["keys"][0]["container"].isEnabled())
        row["mode"].setCurrentIndex(0)
        self.assertTrue(row["add_key"].isEnabled())
        self.assertTrue(row["keys"][0]["container"].isEnabled())

    def test_delete_active_group_requires_confirmation_and_becomes_unconfigured(self):
        row = self.editor.group_rows[0]
        with patch("ui.settings.settings_window.SettingsDialog.question", return_value=QMessageBox.No):
            row["delete_action"].trigger()
        self.assertEqual(len(self.editor.group_rows), 1)
        with patch("ui.settings.settings_window.SettingsDialog.question", return_value=QMessageBox.Yes):
            row["delete_action"].trigger()
        self.assertIsNone(self.presenter.session.groups.active_group_id)
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(self.groups.load().groups, ())

    def test_cross_page_changes_save_atomically_without_changing_legacy_connection(self):
        row = self.editor.group_rows[0]
        row["url"].setText("https://new-group.test/v1")
        row["model"].setText("new-group-model")
        self.window.select_page("appearance")
        self.window.appearance_page.width_input.setValue(400)
        self.window.select_page("ai")
        self.assertEqual(row["model"].text(), "new-group-model")
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(self.groups.load().groups[0].model, "new-group-model")
        self.assertEqual(self.store.get_api("Model"), "old-model")
        self.assertEqual(self.store.get_api("BaseUrl"), "https://example.test/v1")
        self.assertEqual(self.store.get_general_int("Width"), 400)
        self.assertEqual(self.events, ["config_updated"])
        self.assertFalse(self.presenter.session.is_dirty)
        self.presenter.reload()
        self.assertEqual(self.presenter.session.groups, self.groups.load())

    def test_cancel_discards_group_changes_without_creating_file(self):
        original = self.presenter.session.groups
        self.editor.add_group()
        self.presenter.cancel_changes()
        self.assertEqual(self.presenter.session.groups, original)
        self.assertFalse(self.path.exists())

    def test_saved_group_survives_new_settings_instance(self):
        row = self.editor.group_rows[0]
        key = row["keys"][0]
        row["name"].setText("重啟後群組")
        row["model"].setText("restart-model")
        key["priority"].setCurrentIndex(key["priority"].findData(7))
        key["enabled"].setChecked(False)
        self.assertTrue(self.presenter.apply_changes())

        reopened, reopened_presenter = create_settings_window(
            settings_backend=SettingsService(self.store, lambda _event: None),
            group_backend=APIGroupService(self.store, lambda _event: None),
        )
        try:
            restored = reopened.ai_page.group_editor.collect_input().groups[0]
            self.assertEqual(restored.name, "重啟後群組")
            self.assertEqual(restored.model, "restart-model")
            self.assertEqual(restored.keys[0].priority, 7)
            self.assertFalse(restored.keys[0].enabled)
        finally:
            reopened._close_approved = True
            reopened.close()
            reopened.deleteLater()

    def test_close_save_persists_group_draft(self):
        self.editor.group_rows[0]["name"].setText("關閉時儲存")
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question", return_value=QMessageBox.Save):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(self.groups.load().groups[0].name, "關閉時儲存")

    def test_invalid_group_blocks_save_and_keeps_draft(self):
        self.editor.group_rows[0]["url"].setText("bad-url")
        self.window.appearance_page.width_input.setValue(400)
        with patch("ui.settings.settings_window.SettingsDialog.warning"):
            self.assertFalse(self.presenter.apply_changes())
        self.assertFalse(self.path.exists())
        self.assertTrue(self.presenter.session.is_dirty)
        self.assertEqual(self.editor.group_rows[0]["url"].text(), "bad-url")
        self.assertEqual(self.store.get_general_int("Width"), 250)

    def test_failed_save_rolls_back_and_keeps_draft(self):
        self.editor.group_rows[0]["name"].setText("保留草稿")
        real_replace = os.replace
        def fail_group(source, destination):
            if Path(destination) == self.path:
                raise OSError("test failure")
            real_replace(source, destination)
        with (patch("app.core.config_manager.os.replace", side_effect=fail_group),
              patch("ui.settings.settings_window.SettingsDialog.warning"),
              patch("app.presentation.settings.presenter.logger.error")):
            self.assertFalse(self.presenter.apply_changes())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertTrue(self.presenter.session.is_dirty)
        self.assertEqual(self.events, [])

    def test_invalid_close_save_does_not_close(self):
        self.editor.group_rows[0]["model"].clear()
        event = QCloseEvent()
        with (patch("ui.settings.settings_window.SettingsDialog.question", return_value=QMessageBox.Save),
              patch("ui.settings.settings_window.SettingsDialog.warning")):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.path.exists())

    def test_corrupt_group_file_is_disabled_and_preserved(self):
        self.path.write_text("broken data", encoding="utf-8")
        self.presenter.reload()
        self.assertFalse(self.editor.isEnabled())
        self.assertTrue(self.window.ai_page.group_error_label.text())
        self.window.appearance_page.width_input.setValue(400)
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken data")

    def test_minimum_size_group_numeric_buttons_are_separate_and_clickable(self):
        self.window.show()
        self.window.resize(650, 600)
        self.window.select_page("ai")
        row = self.editor.group_rows[0]
        control = row["temperature"]
        self.window.ai_page.ensureWidgetVisible(control)
        self.app.processEvents()
        initial = control.value()
        self.assertFalse(control.editor.geometry().intersects(control.plus_button.geometry()))
        QTest.mouseClick(control.plus_button, Qt.LeftButton)
        self.assertAlmostEqual(control.value(), initial + control.singleStep())


if __name__ == "__main__":
    unittest.main()
