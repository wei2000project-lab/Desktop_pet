import os
import pathlib
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from app.core.window_manager import WindowManager
from app.core.event_bus import event_bus
from tests.settings_helpers import FakeSettingsBackend
from tests.settings_helpers import create_settings_window


class SettingsEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.window, self.presenter = create_settings_window(settings_backend=self.backend)
        self.manager = object.__new__(WindowManager)
        self.manager.settings_window = None
        self.manager.settings_presenter = self.presenter

    def tearDown(self):
        self.window._close_approved = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def open_settings(self):
        with (patch("ui.settings.SettingsWindow", return_value=self.window) as factory,
              patch("app.presentation.settings.presenter.SettingsPresenter", return_value=self.presenter)):
            self.manager.show_settings()
        self.app.processEvents()
        return factory

    def test_entry_creates_settings_once(self):
        self.open_settings().assert_called_once_with()
        self.assertIs(self.manager.settings_window, self.window)
        self.open_settings().assert_not_called()
        self.assertTrue(self.window.isVisible())

    def test_recalling_visible_window_preserves_draft_and_page(self):
        self.open_settings()
        self.window.select_page("appearance")
        self.window.appearance_page.width_input.setValue(400)
        with patch.object(self.presenter, "reload") as reload:
            self.open_settings()
        reload.assert_not_called()
        self.assertEqual(self.window.current_page_key, "appearance")
        self.assertEqual(self.window.appearance_page.width_input.value(), 400)
        self.assertTrue(self.presenter.session.is_dirty)

    def test_minimized_window_is_restored_without_losing_draft(self):
        self.open_settings()
        self.window.ai_page.model_input.setText("draft-model")
        self.window.showMinimized()
        self.app.processEvents()
        self.open_settings()
        self.assertFalse(self.window.isMinimized())
        self.assertEqual(self.window.ai_page.model_input.text(), "draft-model")

    def test_recalling_does_not_reset_running_test_buttons(self):
        self.open_settings()
        row = self.window.ai_page.api_key_rows[0]
        self.window.ai_page.begin_test(row["id"])
        self.window.showMinimized()
        self.app.processEvents()
        self.open_settings()
        self.assertFalse(row["test_button"].isEnabled())
        self.assertEqual(row["test_button"].text(), "測試中")

    def test_reopening_reads_latest_saved_settings(self):
        self.open_settings()
        self.window.close()
        self.backend.snapshot = replace(self.backend.snapshot, width=450, model="new-model")
        self.open_settings().assert_not_called()
        self.assertEqual(self.window.appearance_page.width_input.value(), 450)
        self.assertEqual(self.window.ai_page.model_input.text(), "new-model")
        self.assertFalse(self.presenter.session.is_dirty)

    def test_cancel_then_reopen_restores_saved_values(self):
        self.open_settings()
        self.window.appearance_page.width_input.setValue(400)
        self.presenter.cancel_changes()
        self.open_settings()
        self.assertEqual(self.window.appearance_page.width_input.value(), 250)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_discard_then_reopen_is_clean(self):
        self.open_settings()
        self.window.ai_page.model_input.setText("draft")
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        self.open_settings()
        self.assertEqual(self.window.ai_page.model_input.text(), self.backend.snapshot.model)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_load_failure_does_not_show_stale_settings(self):
        self.manager.settings_window = self.window
        with (patch.object(self.backend, "load", side_effect=RuntimeError("test")),
              patch("app.core.window_manager.logger.error") as error):
            self.manager.show_settings()
        error.assert_called_once()
        self.assertFalse(self.window.isVisible())

    def test_old_window_has_no_remaining_code_references(self):
        self.assertFalse(pathlib.Path("ui/settings_window.py").exists())
        for root in ("app", "ui"):
            for path in pathlib.Path(root).rglob("*.py"):
                self.assertNotIn("ui.settings_window", path.read_text(encoding="utf-8"))
        source = pathlib.Path("ui/pet/desktop_pet.py").read_text(encoding="utf-8")
        self.assertIn('event_bus.publish("show_settings")', source)

    def test_apply_updates_live_pet_and_animator_in_same_process(self):
        from ui.pet.desktop_pet import DesktopPet
        from app.animation.animator import Animator

        class Store:
            values = {"Width": 250, "Height": 250, "ReadingIdleSeconds": 300}
            def get_general(self, key, default=None):
                return self.values.get(key, default)
            def get_general_int(self, key, default):
                return self.values.get(key, default)
            def get_general_bool(self, key, default):
                return self.values.get(key, default)
            def set_general(self, key, value):
                self.values[key] = value

        store = Store()
        listeners_before = {key: list(value) for key, value in event_bus._listeners.items()}
        pet = animator = None
        with (patch("ui.pet.desktop_pet.config_manager", store),
              patch("app.animation.animator.config_manager", store)):
            try:
                pet = DesktopPet()
                animator = Animator()
                original_save = self.backend.save
                def save_and_notify(snapshot):
                    saved = original_save(snapshot)
                    store.values.update(Width=saved.width, Height=saved.height,
                                        AlwaysOnTop=saved.always_on_top,
                                        ReadingIdleSeconds=saved.reading_idle_seconds)
                    event_bus.publish("config_updated")
                    return saved
                self.backend.save = save_and_notify
                self.window.appearance_page.width_input.setValue(400)
                self.window.appearance_page.height_input.setValue(350)
                self.window.general_page.always_on_top_check.setChecked(True)
                self.window.behavior_page.reading_idle_seconds_input.setValue(120)
                self.assertEqual(pet.pet_width, 250)
                self.assertTrue(self.presenter.apply_changes())
                self.app.processEvents()
                self.assertEqual((pet.pet_width, pet.pet_height), (400, 350))
                self.assertEqual((pet.width(), pet.height()), (420, 370))
                self.assertTrue(pet.windowFlags() & Qt.WindowStaysOnTopHint)
                self.assertEqual(animator.idle_to_reading_seconds, 120)
            finally:
                if animator is not None:
                    animator.shutdown()
                for key, callbacks in list(event_bus._listeners.items()):
                    for callback in list(callbacks):
                        if callback not in listeners_before.get(key, []):
                            event_bus.unsubscribe(key, callback)
                if animator is not None:
                    animator.idle_timer.stop()
                    animator.deleteLater()
                if pet is not None:
                    pet.close()
                    pet.deleteLater()


if __name__ == "__main__":
    unittest.main()
