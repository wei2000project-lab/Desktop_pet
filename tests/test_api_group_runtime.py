import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.settings import APIGroupService, APIGroupSettings, SettingsValidationError
from app.settings.api_groups import serialize_api_groups, APIGroupKey
from app.settings.api_group_resolver import resolve_api_request
from app.ai.conversation_manager import ConversationManager
from app.ai.provider import AIProvider
from app.control.execution.request_handler import _complete_with_ai_client
from app.web.service import WebToolService
from tests.test_api_groups import sample_settings
from tests.test_conversation_manager import FakeConfigManager


class RuntimeGroupTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.contents = None
        self.store.get_api_group_contents.side_effect = lambda: self.contents
        self.store.save_api_group_contents.side_effect = self.write
        self.store.get_legacy_api_values.return_value = {
            "baseurl": "https://legacy.test/v1", "model": "legacy-model", "apikey": "synthetic-key"}
        self.service = APIGroupService(self.store, Mock())

    def write(self, contents):
        self.contents = contents

    def test_formal_request_migrates_once(self):
        first = self.service.resolve_runtime_request(environment={})
        second = self.service.resolve_runtime_request(environment={})
        self.assertEqual(first, second)
        self.assertEqual((first.base_url, first.model, first.api_key),
                         ("https://legacy.test/v1", "legacy-model", "synthetic-key"))
        self.store.save_api_group_contents.assert_called_once()

    def test_empty_saved_groups_never_resurrect_legacy(self):
        self.contents = serialize_api_groups(APIGroupSettings())
        with self.assertRaises(SettingsValidationError):
            self.service.resolve_runtime_request(environment={})
        self.store.get_legacy_api_values.assert_not_called()
        self.store.save_api_group_contents.assert_not_called()

    def test_corrupt_groups_never_fallback(self):
        self.contents = "invalid synthetic contents"
        with self.assertRaises(SettingsValidationError):
            self.service.resolve_runtime_request(environment={})
        self.store.get_legacy_api_values.assert_not_called()
        self.assertEqual(self.contents, "invalid synthetic contents")

    def test_priority_disabled_and_environment_isolation(self):
        settings = sample_settings()
        group = replace(settings.groups[0], keys=(
            APIGroupKey("disabled", "X", "disabled-key", 1, False),
            APIGroupKey("later", "後", "later-key", 9),
            APIGroupKey("first", "前", "first-key", 2)))
        self.contents = serialize_api_groups(replace(settings, groups=(group,)))
        snapshot = self.service.resolve_runtime_request(environment={"OPENAI_API_KEY": "unreferenced-key"})
        self.assertEqual(snapshot.api_key, "first-key")
        self.assertEqual([key.id for key in snapshot.candidates], ["first", "later"])

    def test_app_selection_uses_snapshot(self):
        snapshot = resolve_api_request(sample_settings())
        with patch("app.settings.APIGroupService") as backend, patch(
            "app.ai.request_executor.AIRequestExecutor"
        ) as executor:
            backend.return_value.resolve_runtime_request.return_value = snapshot
            executor.return_value.execute.return_value = "selection"
            self.assertEqual(_complete_with_ai_client([{"role": "user", "content": "test"}]), "selection")
        limits = executor.call_args.kwargs["limits"]
        self.assertEqual(limits.operation_timeout, 30.0)
        call = executor.return_value.execute.call_args
        self.assertIs(call.args[0], snapshot)
        self.assertEqual(call.kwargs["max_chars"], 800)

    def test_app_selection_none_mode_uses_real_client(self):
        settings = sample_settings()
        snapshot = resolve_api_request(replace(settings, groups=(replace(settings.groups[0], auth_mode="none"),)))
        with patch("app.settings.APIGroupService") as backend, patch(
            "app.ai.request_executor.AIRequestExecutor"
        ) as executor:
            backend.return_value.resolve_runtime_request.return_value = snapshot
            _complete_with_ai_client([])
        self.assertIs(executor.return_value.execute.call_args.args[0], snapshot)
        executor.return_value.execute.assert_called_once()

    def test_web_decision_none_mode_calls_client(self):
        settings = sample_settings()
        snapshot = resolve_api_request(replace(settings, groups=(replace(settings.groups[0], auth_mode="none"),)))
        executor_factory = Mock()
        executor_factory.return_value.execute.return_value = (
            '{"should_search": false, "query": "", "reason": "test"}'
        )
        service = WebToolService(executor_factory=executor_factory)

        service._decide("最新資料", snapshot, None)

        self.assertEqual(executor_factory.call_args.kwargs["limits"].operation_timeout, 20.0)
        call = executor_factory.return_value.execute.call_args
        self.assertEqual(call.args[0].auth_mode, "none")
        self.assertEqual(call.args[0].temperature, 0.0)


class ConversationGroupTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.snapshot = resolve_api_request(sample_settings())
        self.backend.resolve_runtime_request.return_value = self.snapshot
        self.bus = Mock()
        self.patches = [patch("app.ai.conversation_manager.event_bus", self.bus),
                        patch("app.ai.conversation_manager.config_manager", FakeConfigManager())]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.manager = ConversationManager(group_backend=self.backend)
        self.manager.provider = Mock()
        self.manager.web_tool = Mock()
        self.manager.web_tool.build_context_if_needed.return_value = ""
        self.pending = []
        def thread(*, target, args, **kwargs):
            self.pending.append(lambda: target(*args))
            return SimpleNamespace(start=lambda: None)
        worker = patch("app.ai.conversation_manager.threading.Thread", side_effect=thread)
        worker.start()
        self.addCleanup(worker.stop)

    def test_group_change_during_prepare_keeps_original_snapshot(self):
        self.manager.handle_user_message("你好")
        self.backend.resolve_runtime_request.return_value = replace(self.snapshot, base_url="https://other.test/v1", model="other")
        self.pending.pop(0)()
        request = self.manager.provider.request.call_args.kwargs
        self.assertIs(request["snapshot"], self.snapshot)
        web = self.manager.web_tool.build_context_if_needed.call_args.kwargs
        self.assertIs(web["snapshot"], request["snapshot"])
        self.manager.on_api_error("synthetic-error")
        self.manager.handle_user_message("下一輪")
        self.pending.pop(0)()
        self.assertEqual(self.manager.provider.request.call_args.kwargs["snapshot"].model, "other")

    def test_none_mode_does_not_simulate(self):
        self.backend.resolve_runtime_request.return_value = replace(self.snapshot, auth_mode="none", candidates=())
        self.manager.handle_user_message("你好")
        self.pending.pop(0)()
        self.assertEqual(self.manager.provider.request.call_args.kwargs["snapshot"].auth_mode, "none")

    def test_unconfigured_releases_wait_state_and_no_request(self):
        self.backend.resolve_runtime_request.side_effect = SettingsValidationError("尚未設定群組")
        self.manager.handle_user_message("你好")
        self.assertFalse(self.manager._is_waiting)
        self.manager.provider.request.assert_not_called()
        self.bus.publish.assert_any_call("ai_message_error", "尚未設定群組")
        self.assertEqual(self.pending, [])

    def test_cancel_before_prepare_starts_no_http(self):
        self.manager.handle_user_message("你好")
        self.manager.handle_cancel_requested()
        self.pending.pop(0)()
        self.manager.provider.request.assert_not_called()
        self.manager.provider.cancel.assert_called_once()

    def test_old_callbacks_cannot_update_new_request(self):
        self.manager.handle_user_message("第一輪")
        self.pending.pop(0)()
        old = self.manager.provider.request.call_args.kwargs
        self.manager.handle_cancel_requested()
        self.manager.handle_user_message("第二輪")
        self.pending.pop(0)()
        self.bus.reset_mock()
        old["on_chunk_cb"]("old")
        old["on_finished_cb"]("old")
        old["on_error_cb"]("old")
        self.bus.publish.assert_not_called()


class ProviderCancellationTests(unittest.TestCase):
    def test_new_request_does_not_clear_old_cancellation(self):
        executor_factory = Mock()
        executor_factory.return_value.execute.return_value = "ok"
        provider = AIProvider(executor_factory=executor_factory)
        snapshot = resolve_api_request(sample_settings())
        pending = []
        def thread(*, target, args, **kwargs):
            pending.append(lambda: target(*args))
            return SimpleNamespace(start=lambda: None, is_alive=lambda: False, ident=0)
        finished = Mock()
        error = Mock()
        kwargs = dict(messages=[], snapshot=snapshot, max_chars=0, on_chunk_cb=Mock(),
                      on_finished_cb=finished, on_error_cb=error)
        with patch("app.ai.provider.threading.Thread", side_effect=thread):
            provider.request(**kwargs)
            old_token = provider._cancel_event
            provider.cancel()
            provider.request(**kwargs)
            self.assertTrue(old_token.is_set())
            self.assertFalse(provider._cancel_event.is_set())
            pending[0]()
            executor_factory.assert_not_called()
            pending[1]()
            finished.assert_called_once_with("ok")
            error.assert_not_called()
            self.assertEqual(executor_factory.call_args.kwargs["limits"].operation_timeout, 120.0)
            execute = executor_factory.return_value.execute.call_args
            self.assertIs(execute.args[0], snapshot)

    def test_cancel_stops_active_executor(self):
        executor = Mock()
        provider = AIProvider()
        provider._active_executor = executor

        provider.cancel()

        executor.cancel.assert_called_once_with()
