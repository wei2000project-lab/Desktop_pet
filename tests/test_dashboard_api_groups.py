import configparser
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QGridLayout, QLineEdit, QMessageBox

from app.core.config_manager import ConfigManager
from app.settings import APIGroupService, SettingsService
from app.settings.api_groups import serialize_api_groups, validate_api_groups
from ui.dashboard import DashboardWindow
from tests.test_dashboard_api_keys import FakePool, FakeWorker
from app.ai.client import AIClient


class DashboardAPIGroupTests(unittest.TestCase):
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
        self.window = DashboardWindow(settings_backend=self.settings, group_backend=self.groups)
        self.editor = self.window.ai_page.group_editor
        self.path = Path(self.store.api_groups_json_path)

    def tearDown(self):
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_initial_preview_is_clean_and_does_not_migrate_to_disk(self):
        self.assertFalse(self.window.is_dirty)
        self.assertFalse(self.path.exists())
        group = self.editor.collect_settings().groups[0]
        self.assertEqual((group.base_url, group.model, group.verify_ssl), ("https://example.test/v1", "old-model", False))
        self.assertEqual(group.keys[0].key, "fake-stored-key")
        self.assertEqual(self.events, [])

    def start_test(self, key=True):
        controller = self.window.connection_tests
        controller.pool = FakePool()
        controller.worker_factory = FakeWorker
        group = self.editor.group_rows[0]
        row = group["keys"][0] if key else group
        controller.start_group(group["id"], row["id"] if key else "")
        return controller, group, row

    def test_group_check_uses_draft_without_saving(self):
        controller, group, row = self.start_test()
        self.assertEqual(controller.pool.workers[0].inputs,
                         ("https://example.test/v1", "fake-stored-key", "old-model", False))
        self.assertFalse(row["test_button"].isEnabled())
        self.assertFalse(row["name"].isEnabled())
        self.assertFalse(self.path.exists())
        self.assertFalse(self.window.is_dirty)
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
        self.editor.load_settings(self.editor.collect_settings())
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
        self.assertTrue(self.window.apply_changes())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.get_api("Model"), "old-model")
        self.assertFalse(self.window.is_dirty)

    def test_formal_group_ui_hides_legacy_cards_and_keeps_memory(self):
        self.assertTrue(self.window.ai_page._group_mode)
        self.assertTrue(all(card.isHidden() for card in self.window.ai_page._legacy_cards))
        self.window.ai_page.max_memory_turns_input.setValue(3)
        self.assertTrue(self.window.apply_changes())
        self.assertEqual(self.store.get_general_int("MaxMemoryTurns"), 3)
        self.assertFalse(self.path.exists())

    def test_group_apply_preserves_legacy_file_bytes(self):
        legacy = Path(self.store.api_ini_path)
        original = b"[API]\nModel=original-preserved\nApiKey=synthetic-original-key\n"
        # Test fixture only; create the original file through the production atomic writer.
        from app.core.config_manager import write_text_bundle_atomically
        write_text_bundle_atomically({legacy: original.decode()})
        self.editor.group_rows[0]["name"].setText("修改群組")
        self.assertTrue(self.window.apply_changes())
        self.assertEqual(legacy.read_bytes(), original)

    def test_invalid_hidden_legacy_fields_do_not_block_group_save(self):
        self.store.api_config.set("API", "BaseUrl", "")
        self.store.api_config.set("API", "Model", "")
        self.window._draft_snapshot = replace(self.window._draft_snapshot, base_url="", model="")
        self.editor.group_rows[0]["name"].setText("有效群組")
        self.assertTrue(self.window.apply_changes())

    def test_rename_preserves_group_and_key_ids(self):
        row = self.editor.group_rows[0]
        original = self.editor.collect_settings()
        row["name"].setText("重新命名")
        edited = self.editor.collect_settings()
        self.assertEqual(edited.groups[0].id, original.groups[0].id)
        self.assertEqual(edited.groups[0].keys[0].id, original.groups[0].keys[0].id)
        self.assertEqual(edited.active_group_id, original.active_group_id)
        self.assertTrue(self.window.is_dirty)

    def test_add_has_valid_defaults_and_does_not_switch_active(self):
        active = self.editor.collect_settings().active_group_id
        row = self.editor.add_group()
        settings = self.editor.collect_settings()
        validate_api_groups(settings)
        self.assertEqual(settings.active_group_id, active)
        self.assertNotEqual(row["id"], active)
        self.editor.set_active(row["id"])
        self.assertEqual(self.window._draft_groups.active_group_id, row["id"])
        self.assertFalse(self.path.exists())

    def test_editing_selection_is_separate_from_active_group(self):
        active = self.editor.collect_settings().active_group_id
        added = self.editor.add_group()
        self.assertEqual(self.editor.selected_group_id, added["id"])
        self.assertEqual(self.editor.collect_settings().active_group_id, active)
        self.assertIn("編輯中", added["list_button"].text())
        draft = self.editor.collect_settings()
        first = self.editor.group_rows[0]
        first["list_button"].click()
        self.assertEqual(self.editor.selected_group_id, first["id"])
        self.assertEqual(self.editor.collect_settings().active_group_id, active)
        self.assertEqual(self.editor.collect_settings(), draft)

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
        with patch("ui.dashboard.dashboard_window.QMessageBox.warning") as warning:
            self.assertFalse(self.window.apply_changes())
        self.assertIn("不要包含 /chat/completions", warning.call_args.args[2])
        self.assertTrue(self.window.is_dirty)

    def test_editing_selection_survives_reload_and_moves_after_delete(self):
        first = self.editor.group_rows[0]
        second = self.editor.add_group()
        settings = self.editor.collect_settings()
        self.editor.load_settings(settings)
        self.assertEqual(self.editor.selected_group_id, second["id"])
        self.editor.remove_group(second["id"])
        self.assertEqual(self.editor.selected_group_id, first["id"])
        self.assertEqual(self.editor.collect_settings().active_group_id, first["id"])

    def test_collapsing_and_revealing_do_not_dirty(self):
        row = self.editor.group_rows[0]
        row["toggle"].click()
        self.assertFalse(row["advanced_body"].isHidden())
        row["toggle"].click()
        self.assertTrue(row["advanced_body"].isHidden())
        key = row["keys"][0]
        key["show"].click()
        self.assertEqual(key["key"].echoMode(), QLineEdit.Normal)
        key["show"].click()
        self.assertEqual(key["key"].echoMode(), QLineEdit.Password)
        self.assertFalse(self.window.is_dirty)

    def test_responsive_layout_reflows_master_detail_and_key_fields(self):
        row = self.editor.group_rows[0]
        key = row["keys"][0]
        self.editor._update_responsive_layout(800)
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.LeftToRight)
        wide_source_row = key["layout"].getItemPosition(key["layout"].indexOf(key["source"]))[0]
        self.editor._update_responsive_layout(520)
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.TopToBottom)
        narrow_source_row = key["layout"].getItemPosition(key["layout"].indexOf(key["source"]))[0]
        self.assertEqual(wide_source_row, 0)
        self.assertEqual(narrow_source_row, 1)
        self.assertEqual(self.editor.group_list_pane.maximumWidth(), 16777215)

    def test_dashboard_window_drives_wide_and_narrow_api_layouts(self):
        self.window.select_page("ai")
        self.window.show()
        self.window.resize(900, 760)
        self.app.processEvents()
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.LeftToRight)
        self.window.resize(650, 600)
        self.app.processEvents()
        self.assertEqual(self.editor.master_detail_layout.direction(), QBoxLayout.TopToBottom)

    def test_priority_and_x_keep_previous_priority(self):
        key = self.editor.group_rows[0]["keys"][0]
        key["priority"].setValue(5)
        key["enabled"].setChecked(False)
        settings = self.editor.collect_settings()
        self.assertFalse(settings.groups[0].keys[0].enabled)
        self.assertEqual(settings.groups[0].keys[0].priority, 5)
        key["enabled"].setChecked(True)
        self.assertEqual(self.editor.collect_settings().groups[0].keys[0].priority, 5)

    def test_unavailable_active_group_is_clearly_marked(self):
        key = self.editor.group_rows[0]["keys"][0]
        key["enabled"].setChecked(False)
        self.assertIn("全部已暫停", self.editor.state_label.text())

    def test_unedited_legacy_temperature_precision_is_preserved(self):
        settings = self.editor.collect_settings()
        settings = replace(settings, groups=(replace(settings.groups[0], temperature=0.75),))
        self.editor.load_settings(settings)
        self.assertEqual(self.editor.group_rows[0]["temperature"].value(), 0.75)
        self.editor.group_rows[0]["name"].setText("改名但不改溫度")
        self.assertEqual(self.editor.collect_settings().groups[0].temperature, 0.75)

    def test_blank_new_key_row_is_not_persisted_or_dirty(self):
        group = self.editor.group_rows[0]
        self.editor.add_key(group["id"])
        self.assertFalse(self.window.is_dirty)
        self.assertEqual(len(self.editor.collect_settings().groups[0].keys), 1)
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
            settings = self.editor.collect_settings()
            self.assertEqual(key["key"].text(), "")
            self.assertFalse(key["key"].isEnabled())
            self.assertFalse(key["show"].isEnabled())
            self.assertIn("已設定", key["status"].text())
            self.assertTrue(self.window.apply_changes())
        self.assertNotIn("fake-env-secret", serialize_api_groups(settings))
        self.assertNotIn("fake-env-secret", self.path.read_text(encoding="utf-8"))

    def test_none_mode_keeps_key_list(self):
        row = self.editor.group_rows[0]
        row["mode"].setCurrentIndex(1)
        settings = self.editor.collect_settings()
        self.assertEqual(settings.groups[0].auth_mode, "none")
        self.assertEqual(settings.groups[0].keys[0].key, "fake-stored-key")
        self.assertFalse(row["add_key"].isEnabled())
        self.assertFalse(row["keys"][0]["container"].isEnabled())
        row["mode"].setCurrentIndex(0)
        self.assertTrue(row["add_key"].isEnabled())
        self.assertTrue(row["keys"][0]["container"].isEnabled())

    def test_delete_active_group_requires_confirmation_and_becomes_unconfigured(self):
        row = self.editor.group_rows[0]
        with patch("ui.dashboard.api_group_editor.QMessageBox.question", return_value=QMessageBox.No):
            row["delete_button"].click()
        self.assertEqual(len(self.editor.group_rows), 1)
        with patch("ui.dashboard.api_group_editor.QMessageBox.question", return_value=QMessageBox.Yes):
            row["delete_button"].click()
        self.assertIsNone(self.editor.collect_settings().active_group_id)
        self.assertTrue(self.window.apply_changes())
        self.assertEqual(self.groups.load().groups, ())

    def test_cross_page_changes_save_atomically_without_changing_legacy_connection(self):
        row = self.editor.group_rows[0]
        row["url"].setText("https://new-group.test/v1")
        row["model"].setText("new-group-model")
        self.window.select_page("appearance")
        self.window.appearance_page.width_input.setValue(400)
        self.window.select_page("ai")
        self.assertEqual(row["model"].text(), "new-group-model")
        self.assertTrue(self.window.apply_changes())
        self.assertEqual(self.groups.load().groups[0].model, "new-group-model")
        self.assertEqual(self.store.get_api("Model"), "old-model")
        self.assertEqual(self.store.get_api("BaseUrl"), "https://example.test/v1")
        self.assertEqual(self.store.get_general_int("Width"), 400)
        self.assertEqual(self.events, ["config_updated"])
        self.assertFalse(self.window.is_dirty)
        self.window.load_settings()
        self.assertEqual(self.editor.collect_settings(), self.groups.load())

    def test_cancel_discards_group_changes_without_creating_file(self):
        original = self.editor.collect_settings()
        self.editor.add_group()
        self.window.cancel_changes()
        self.assertEqual(self.editor.collect_settings(), original)
        self.assertFalse(self.path.exists())

    def test_invalid_group_blocks_save_and_keeps_draft(self):
        self.editor.group_rows[0]["url"].setText("bad-url")
        self.window.appearance_page.width_input.setValue(400)
        with patch("ui.dashboard.dashboard_window.QMessageBox.warning"):
            self.assertFalse(self.window.apply_changes())
        self.assertFalse(self.path.exists())
        self.assertTrue(self.window.is_dirty)
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
              patch("ui.dashboard.dashboard_window.QMessageBox.warning"),
              patch("ui.dashboard.dashboard_window.logger.error")):
            self.assertFalse(self.window.apply_changes())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertTrue(self.window.is_dirty)
        self.assertEqual(self.events, [])

    def test_invalid_close_save_does_not_close(self):
        self.editor.group_rows[0]["model"].clear()
        event = QCloseEvent()
        with (patch("ui.dashboard.dashboard_window.QMessageBox.question", return_value=QMessageBox.Save),
              patch("ui.dashboard.dashboard_window.QMessageBox.warning")):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.path.exists())

    def test_corrupt_group_file_is_disabled_and_preserved(self):
        self.path.write_text("broken data", encoding="utf-8")
        self.window.load_settings()
        self.assertFalse(self.editor.isEnabled())
        self.assertTrue(self.window.ai_page.group_error_label.text())
        self.window.appearance_page.width_input.setValue(400)
        self.assertTrue(self.window.apply_changes())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken data")

    def test_minimum_size_group_numeric_buttons_are_separate_and_clickable(self):
        self.window.show()
        self.window.resize(650, 600)
        self.window.select_page("ai")
        row = self.editor.group_rows[0]
        for control in (row["temperature"], row["keys"][0]["priority"]):
            self.window.ai_page.ensureWidgetVisible(control)
            self.app.processEvents()
            initial = control.value()
            self.assertFalse(control.editor.geometry().intersects(control.plus_button.geometry()))
            QTest.mouseClick(control.plus_button, Qt.LeftButton)
            self.assertAlmostEqual(control.value(), initial + control.singleStep())


if __name__ == "__main__":
    unittest.main()
