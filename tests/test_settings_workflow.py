from app.settings.display import settings_display
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal

from app.presentation.settings.connection_test_controller import ConnectionTestController
from app.presentation.settings.presenter import SettingsPresenter
from app.settings.session import SettingsSession
from app.contracts.settings import CloseChoice, CloseRequest, ConnectionInputs
from tests.settings_helpers import FakePool, FakeSettingsBackend, FakeWorker


class FakeView(QObject):
    """A view port with no widgets, usable without a QApplication."""
    settings_changed = Signal(dict)
    groups_changed = Signal(object)
    apply_requested = Signal()
    cancel_requested = Signal()
    clear_history_requested = Signal()
    close_requested = Signal(object)
    closed = Signal()
    legacy_test_requested = Signal(int)
    group_test_requested = Signal(str, str)
    add_group_requested = Signal()
    add_key_requested = Signal(str)
    delete_group_requested = Signal(str)

    def __init__(self):
        super().__init__()
        for name in (
            "load_snapshot", "load_groups", "show_group_feedback", "show_dirty_state",
            "show_saved", "show_warning", "show_history_cleared", "commit_pending_input",
            "close_without_prompt", "set_personality_options", "show_test_started",
            "show_test_finished", "add_api_group", "add_api_key", "remove_api_group",
        ):
            setattr(self, name, Mock())
        self.connection_inputs = Mock(return_value=ConnectionInputs())
        self.confirm_close = Mock(return_value=CloseChoice.CANCEL)
        self.confirm_clear_history = Mock(return_value=False)
        self.confirm_group_delete = Mock(return_value=False)


class SettingsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.session = SettingsSession(self.backend)
        self.view = FakeView()
        self.presenter = SettingsPresenter(self.view, self.session)

    def tearDown(self):
        self.view.deleteLater()

    def test_view_events_drive_save_without_access_to_widgets(self):
        self.view.settings_changed.emit({"width": 400})
        self.view.show_dirty_state.assert_called_with(True)
        self.assertEqual(self.backend.saved, [])
        self.view.apply_requested.emit()
        self.assertEqual(self.backend.saved[0].width, 400)
        self.view.commit_pending_input.assert_called_once()
        self.view.load_snapshot.assert_called_with(settings_display(self.backend.snapshot))
        self.view.show_saved.assert_called_once()

    def test_cancel_restores_snapshot_before_requesting_view_close(self):
        self.view.settings_changed.emit({"width": 400})
        self.view.cancel_requested.emit()
        self.assertEqual(self.backend.saved, [])
        self.assertFalse(self.session.is_dirty)
        self.view.load_snapshot.assert_called_with(settings_display(self.backend.snapshot))
        self.view.close_without_prompt.assert_called_once()

    def test_close_choice_and_failed_save_are_decided_in_application_layer(self):
        self.view.settings_changed.emit({"width": 400})
        request = CloseRequest()
        self.view.close_requested.emit(request)
        self.assertFalse(request.accepted)
        self.assertTrue(self.session.is_dirty)
        self.view.confirm_close.return_value = CloseChoice.SAVE
        with (patch.object(self.backend, "save", side_effect=OSError("private-details")),
              patch("app.presentation.settings.presenter.logger.error")):
            self.view.close_requested.emit(request)
        self.assertFalse(request.accepted)
        self.view.show_warning.assert_called_with("儲存失敗", "設定未完整儲存，請稍後再試。")
        self.view.confirm_close.return_value = CloseChoice.DISCARD
        self.view.close_requested.emit(request)
        self.assertTrue(request.accepted)
        self.assertFalse(self.session.is_dirty)

    def test_history_clear_requires_positive_confirmation(self):
        self.view.clear_history_requested.emit()
        self.assertEqual(self.backend.history_clear_count, 0)
        self.view.confirm_clear_history.return_value = True
        self.view.clear_history_requested.emit()
        self.assertEqual(self.backend.history_clear_count, 1)
        self.view.show_history_cleared.assert_called_once()


class SettingsConnectionControllerTests(unittest.TestCase):
    def setUp(self):
        self.session = SettingsSession(FakeSettingsBackend())
        self.inputs = ConnectionInputs({1: "test-key"})
        self.pool = FakePool()
        self.controller = ConnectionTestController(
            self.session, lambda: self.inputs, pool=self.pool, worker_factory=FakeWorker)
        self.results = []
        self.controller.finished.connect(lambda target, message: self.results.append((target, message)))

    def tearDown(self):
        self.controller.deleteLater()

    def test_changed_inputs_make_background_result_stale_without_widgets(self):
        self.controller.start(1)
        self.session.update({"model": "different-model"})
        self.pool.workers[0].finish()
        self.assertEqual(self.results[0][1], "設定已變更，請重新測試。")

    def test_removed_input_and_invalidated_session_ignore_late_results(self):
        self.controller.start(1)
        self.inputs = ConnectionInputs()
        self.pool.workers[0].finish()
        self.assertEqual(self.results, [])
        self.inputs = ConnectionInputs({2: "test-key"})
        self.controller.start(2)
        self.controller.invalidate()
        self.pool.workers[1].finish()
        self.assertEqual(self.results, [])
        self.assertEqual(self.controller._jobs, {})

    def test_submission_failure_releases_slot_and_returns_safe_error(self):
        with patch.object(self.pool, "start", side_effect=RuntimeError("private-details")):
            self.controller.start(1)
        self.assertEqual(self.controller._jobs, {})
        self.assertEqual(self.results[0][1], "無法啟動連線測試，請稍後再試。")
        self.controller.start(1)
        self.assertEqual(len(self.pool.workers), 1)

    def test_duplicate_and_old_session_jobs_share_bounded_capacity(self):
        self.inputs = ConnectionInputs({number: "test-key" for number in range(1, 7)})
        self.controller.start(1)
        self.controller.start(1)
        self.assertEqual(len(self.pool.workers), 1)
        self.controller.invalidate()
        for number in range(2, 6):
            self.controller.start(number)
        self.assertEqual(len(self.pool.workers), 4)
        self.assertIn("多個測試", self.results[-1][1])


class SettingsMultipleViewsTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.left_session = SettingsSession(self.backend)
        self.right_session = SettingsSession(self.backend)
        self.left, self.right = FakeView(), FakeView()
        self.left_presenter = SettingsPresenter(self.left, self.left_session)
        self.right_presenter = SettingsPresenter(self.right, self.right_session)
        for view, presenter in ((self.left, self.left_presenter), (self.right, self.right_presenter)):
            view.connection_inputs.return_value = ConnectionInputs({1: "fake-key"})
            presenter.connection_tests.pool = FakePool()
            presenter.connection_tests.worker_factory = FakeWorker

    def tearDown(self):
        self.left.deleteLater()
        self.right.deleteLater()

    def test_shared_backend_does_not_share_drafts_or_cancel_state(self):
        self.left.settings_changed.emit({"width": 400})
        self.right.settings_changed.emit({"width": 600})
        self.left.apply_requested.emit()
        self.assertEqual(self.backend.snapshot.width, 400)
        self.assertFalse(self.left_session.is_dirty)
        self.assertEqual(self.right_session.snapshot.width, 600)
        self.assertTrue(self.right_session.is_dirty)
        self.right.cancel_requested.emit()
        self.assertEqual(self.right_session.snapshot.width, 250)
        self.assertEqual(self.left_session.snapshot.width, 400)
        self.assertEqual(len(self.backend.saved), 1)
        self.left.close_without_prompt.assert_not_called()
        self.right.close_without_prompt.assert_called_once()
        self.right_presenter.reload()
        self.assertEqual(self.right_session.snapshot.width, 400)

    def test_same_request_ids_return_only_to_originating_view_after_other_view_closes(self):
        self.left.legacy_test_requested.emit(1)
        self.right.legacy_test_requested.emit(1)
        left_worker = self.left_presenter.connection_tests.pool.workers[0]
        right_worker = self.right_presenter.connection_tests.pool.workers[0]
        self.assertEqual(left_worker.request_id, right_worker.request_id)
        self.left.closed.emit()
        self.left_presenter.reload()
        left_worker.finish(message="old left result")
        self.left.show_test_finished.assert_not_called()
        self.right.show_test_finished.assert_not_called()
        right_worker.finish(message="right result")
        self.assertEqual(self.right.show_test_finished.call_args.args[1], "right result")
        self.left.show_test_finished.assert_not_called()
        self.left.legacy_test_requested.emit(1)
        self.left_presenter.connection_tests.pool.workers[1].finish(message="new left result")
        self.assertEqual(self.left.show_test_finished.call_args.args[1], "new left result")
        self.right.show_test_finished.assert_called_once()

    def test_group_load_baselines_and_new_rows_are_session_local(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from app.contracts.settings import APIGroupInput, APIKeyInput, APIGroupsInput
        from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
        groups = APIGroupSettings((APIGroup(
            "g", "Group", "https://example.test/v1", "model",
            keys=(APIGroupKey("k", "Key", environment_variable="FAKE_SAVED"),),
        ),), "g", 2)
        backend = SimpleNamespace(load=lambda: groups)
        left = SettingsSession(self.backend, backend)
        right = SettingsSession(self.backend, backend)
        left.display_groups()
        right.display_groups()
        raw_key = APIKeyInput("k", "Key", "fake-display", 1, True, "stored", False)
        form = APIGroupsInput((APIGroupInput(
            "g", "Group", "https://example.test/v1", "model", 0.7,
            True, "api_key", (raw_key,), False,
        ),), "g")
        left.update_group_input(replace(form, groups=(replace(form.groups[0],
            keys=(replace(raw_key, source="environment"),)),)))
        new_key = right.new_key_display("g")
        right.update_group_input(form)
        self.assertEqual(left.groups.groups[0].keys[0].source, "environment")
        self.assertEqual(right.groups, groups)
        left.update_group_input(form)
        self.assertEqual(left.groups, groups)
        added_key = APIKeyInput(new_key.id, "New Key", "fake-new-key", new_key.priority,
                                new_key.enabled, new_key.source, True)
        right.update_group_input(replace(form, groups=(replace(form.groups[0],
            keys=(raw_key, added_key)),)))
        self.assertEqual(tuple(key.id for key in right.groups.groups[0].keys), ("k", new_key.id))
        self.assertEqual(right.groups.groups[0].keys[1].key, "fake-new-key")
        self.assertEqual(left.groups, groups)
        right.discard()
        self.assertEqual(right.groups, groups)
        self.assertEqual(left.groups, groups)


if __name__ == "__main__":
    unittest.main()
