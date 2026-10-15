"""Coordinate settings operations through view methods; never inspect widgets."""
from PySide6.QtCore import QObject

from app.ai.prompt_builder import get_personality_option_labels
from app.settings.connection_test_controller import ConnectionTestController
from app.settings.editing import group_feedback, new_api_group, new_api_key
from app.settings.model import SettingsValidationError
from app.settings.session import SettingsSession
from app.contracts.settings import CloseChoice
from app.presentation.settings.view_port import SettingsView
from app.utils.logger import logger


class SettingsPresenter(QObject):
    def __init__(self, view: SettingsView, session=None):
        super().__init__(view)
        self.view = view
        self.session = SettingsSession() if session is None else session
        self.connection_tests = ConnectionTestController(self.session, view.connection_inputs, parent=self)
        view.settings_changed.connect(self.update)
        view.groups_changed.connect(self.update_groups)
        view.apply_requested.connect(self.apply_changes)
        view.cancel_requested.connect(self.cancel_changes)
        view.clear_history_requested.connect(self.clear_history)
        view.close_requested.connect(self.request_close)
        view.closed.connect(self.connection_tests.invalidate)
        view.legacy_test_requested.connect(self.start_legacy_test)
        view.group_test_requested.connect(self.start_group_test)
        view.add_group_requested.connect(self.add_group)
        view.add_key_requested.connect(self.add_key)
        view.delete_group_requested.connect(self.delete_group)
        self.connection_tests.started.connect(view.show_test_started)
        self.connection_tests.finished.connect(view.show_test_finished)
        view.set_personality_options({**get_personality_option_labels(), "custom": "使用自訂人格 Prompt"})
        self.render()

    def render(self):
        self.view.load_snapshot(self.session.snapshot)
        self.view.load_groups(self.session.groups, self.session.group_mode, self.session.group_error)
        self.view.show_group_feedback(group_feedback(self.session.groups))
        self.view.show_dirty_state(self.session.is_dirty)

    def update(self, values):
        self.session.update(values)
        self.view.show_dirty_state(self.session.is_dirty)

    def update_groups(self, groups):
        self.session.update_groups(groups)
        self.view.show_group_feedback(group_feedback(self.session.groups))
        self.view.show_dirty_state(self.session.is_dirty)

    def apply_changes(self):
        self.view.commit_pending_input()
        try:
            self.session.apply()
        except SettingsValidationError as error:
            self.view.show_warning("設定內容無效", str(error))
            return False
        except Exception:
            logger.error("Failed to save settings", exc_info=True)
            self.view.show_warning("儲存失敗", "設定未完整儲存，請稍後再試。")
            return False
        self.connection_tests.invalidate()
        self.render()
        self.view.show_saved()
        return True

    def discard(self):
        self.session.discard()
        self.connection_tests.invalidate()
        self.render()

    def cancel_changes(self):
        self.discard()
        self.view.close_without_prompt()

    def reload(self):
        self.session.reload()
        self.connection_tests.invalidate()
        self.render()

    def clear_history(self):
        if not self.view.confirm_clear_history():
            return
        try:
            self.session.clear_history()
        except Exception:
            logger.error("Failed to clear conversation history", exc_info=True)
            self.view.show_warning("刪除失敗", "無法刪除對話紀錄，請稍後再試。")
            return
        self.view.show_history_cleared()

    def request_close(self, request):
        if not self.session.is_dirty:
            request.accepted = True
            return
        choice = self.view.confirm_close()
        if choice is CloseChoice.SAVE:
            request.accepted = self.apply_changes()
        elif choice is CloseChoice.DISCARD:
            self.discard()
            request.accepted = True
        else:
            request.accepted = False

    def start_legacy_test(self, row_id):
        self.view.commit_pending_input()
        self.connection_tests.start(row_id)

    def start_group_test(self, group_id, key_id):
        self.view.commit_pending_input()
        self.connection_tests.start_group(group_id, key_id)

    def add_group(self):
        self.view.add_api_group(new_api_group())

    def add_key(self, group_id):
        self.view.add_api_key(group_id, new_api_key())

    def delete_group(self, group_id):
        if self.view.confirm_group_delete(group_id == self.session.groups.active_group_id):
            self.view.remove_api_group(group_id)
