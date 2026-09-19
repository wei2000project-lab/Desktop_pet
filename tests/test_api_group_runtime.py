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
        with patch("app.settings.APIGroupService") as backend, patch("app.ai.client.AIClient") as client:
            backend.return_value.resolve_runtime_request.return_value = snapshot
            client.return_value.request_completion.return_value = "selection"
            self.assertEqual(_complete_with_ai_client([{"role": "user", "content": "test"}]), "selection")
        self.assertEqual(client.call_args.kwargs["base_url"], snapshot.base_url)
        self.assertEqual(client.call_args.kwargs["api_key"], snapshot.api_key)
        self.assertEqual(client.return_value.request_completion.call_args.kwargs["temperature"], snapshot.temperature)

    def test_app_selection_none_mode_uses_real_client(self):
        settings = sample_settings()
        snapshot = resolve_api_request(replace(settings, groups=(replace(settings.groups[0], auth_mode="none"),)))
        with patch("app.settings.APIGroupService") as backend, patch("app.ai.client.AIClient") as client:
            backend.return_value.resolve_runtime_request.return_value = snapshot
            _complete_with_ai_client([])
        self.assertIsNone(client.call_args.kwargs["api_key"])
        client.return_value.request_completion.assert_called_once()

    def test_web_decision_none_mode_calls_client(self):
        service = WebToolService()
        with patch("app.ai.client.AIClient") as client:
            client.return_value.request_completion.return_value = '{"should_search": false, "query": "", "reason": "test"}'
            service._decide("最新資料", "http://localhost:8080/v1", None, "local", True, None)
        self.assertIsNone(client.call_args.args[1])
        client.return_value.request_completion.assert_called_once()


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
        self.assertEqual((request["api_url"], request["model"], request["api_key"]),
                         (self.snapshot.base_url, self.snapshot.model, self.snapshot.api_key))
        web = self.manager.web_tool.build_context_if_needed.call_args.kwargs
        self.assertEqual(web["api_url"], request["api_url"])
        self.assertEqual(web["api_key"], request["api_key"])
        self.manager.on_api_error("synthetic-error")
        self.manager.handle_user_message("下一輪")
        self.pending.pop(0)()
        self.assertEqual(self.manager.provider.request.call_args.kwargs["model"], "other")

    def test_none_mode_does_not_simulate(self):
        self.backend.resolve_runtime_request.return_value = replace(self.snapshot, auth_mode="none", candidates=())
        self.manager.handle_user_message("你好")
        self.pending.pop(0)()
        self.assertIsNone(self.manager.provider.request.call_args.kwargs["api_key"])

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
        provider = AIProvider()
        pending = []
        def thread(*, target, args, **kwargs):
            pending.append(lambda: target(*args))
            return SimpleNamespace(start=lambda: None, is_alive=lambda: False, ident=0)
        finished = Mock()
        error = Mock()
        kwargs = dict(messages=[], api_url="https://example.test/v1", api_key=None, model="local",
                      temperature=0.7, max_chars=0, verify_ssl=True, on_chunk_cb=Mock(),
                      on_finished_cb=finished, on_error_cb=error)
        with patch("app.ai.provider.threading.Thread", side_effect=thread), patch("app.ai.provider.AIClient") as client:
            client.return_value.request_completion.return_value = "ok"
            provider.request(**kwargs)
            old_token = provider._cancel_event
            provider.cancel()
            provider.request(**kwargs)
            self.assertTrue(old_token.is_set())
            self.assertFalse(provider._cancel_event.is_set())
            pending[0]()
            client.assert_not_called()
            pending[1]()
            finished.assert_called_once_with("ok")
            error.assert_not_called()
